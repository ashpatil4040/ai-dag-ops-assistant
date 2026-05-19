# Infrastructure & Architecture

## System Overview

AI DAG Ops Assistant is a FastAPI webhook server that listens for Jira tickets and autonomously performs Airflow DAG operations — from reading and validating existing DAGs to generating new ones with AI. Every code-changing operation creates a Git branch, commits the change, pushes to GitHub, and opens a draft Pull Request.

```
Jira Cloud  ──webhook──►  FastAPI (port 8080)  ──►  Classifier + Bedrock Planner
                                │
                    ┌───────────┴───────────┐
                    │                       │
              Read-only ops          Code-changing ops
          (READ, VALIDATE,        (CREATE, MODIFY, DISABLE,
           DEBUG_DAG_FAILURE)      DEPRECATE, ARCHIVE_DAG)
                    │                       │
              Jira comment          DAG Generator / AI Code Gen
                                           │
                                     Git branch + commit
                                           │
                                    GitHub draft PR
                                           │
                                     Jira comment
```

---

## Components

### 1. Ingress — ngrok + FastAPI

| Layer | Detail |
|---|---|
| Public URL | ngrok tunnel (HTTPS) → `localhost:8080` |
| Server | uvicorn running `app.main:app` |
| Endpoint | `POST /webhooks/jira` — receives Jira Cloud webhook payloads |
| Health | `GET /` — returns `{"status": "running"}` |

Jira Cloud sends an `issue_created` or `issue_updated` webhook to the ngrok URL. The payload is Atlassian Document Format (ADF); the server parses it to plain text before processing.

---

### 2. Classification Pipeline

```
JiraTicket  ──►  Classifier  ──►  TicketClassification
                     │                   │
             keyword matching      Bedrock Planner override
             (classifier.py)       (bedrock_planner.py)
```

**Classifier** (`app/classifier.py`) — fast keyword-based first pass. Keyword check order is critical:

1. `delete` → DEPRECATE_DAG + CRITICAL + safety_warning (DELETE is blocked)
2. `archive` → ARCHIVE_DAG, CRITICAL
3. `disable` / `pause` → DISABLE_DAG, HIGH
4. `deprecate` / `sunset` / `retire` / `decommission` → DEPRECATE_DAG, HIGH
5. `create` / `new dag` → CREATE_DAG, MEDIUM
6. `modify` / `update` / `change` → MODIFY_DAG, HIGH
7. `debug` / `broken` / `dag failure` / `task failed` → DEBUG_DAG_FAILURE, MEDIUM
8. `show me` / `inspect` / `describe` → READ_DAG, LOW
9. `validate` / `check` → VALIDATE_DAG, LOW

**Bedrock Planner** (`app/bedrock_planner.py`) — AI second pass using `us.amazon.nova-micro-v1:0`. Extracts structured fields (dag_id, source, target, schedule, etc.) and may correct the operation classification. Override rules:
- **Never overrides** ARCHIVE_DAG (Bedrock can misread "deprecated for 90 days" in descriptions)
- **Never overrides** the DELETE→DEPRECATE safety redirect
- **Always overrides** operation + risk_level for all other cases

---

### 3. AWS Bedrock Integration

| Purpose | Model | Max Tokens | Timeout |
|---|---|---|---|
| Planning / classification | `us.amazon.nova-micro-v1:0` | 1024 | 30s read |
| AI DAG code generation | `us.amazon.nova-pro-v1:0` | 2500 | 90s read |
| AI test code generation | `us.amazon.nova-pro-v1:0` | 1500 | 90s read |

Authentication uses the default boto3 credential chain (environment variables, `~/.aws/credentials`, or IAM role).

Feature flags in `.env`:
```
USE_BEDROCK_PLANNER=true       # enable Bedrock planning
USE_AI_CODE_GENERATOR=true     # enable AI DAG code generation (vs Jinja2 templates)
```

---

### 4. DAG Operations

| Operation | Type | Output |
|---|---|---|
| `READ_DAG` | Read-only | DAG metadata (tasks, schedule, owner, etc.) |
| `VALIDATE_DAG` | Read-only | Policy + security + syntax validation report |
| `DEBUG_DAG_FAILURE` | Read-only | Bedrock root-cause analysis + recommendations |
| `CREATE_DAG` | Code-changing | New DAG file (AI or Jinja2 template) |
| `MODIFY_DAG` | Code-changing | Updated DAG file |
| `DISABLE_DAG` | Code-changing | DAG with `schedule=None`, `is_paused_upon_creation=True` |
| `DEPRECATE_DAG` | Code-changing | DAG with deprecated tag + schedule cleared |
| `ARCHIVE_DAG` | Code-changing | DAG moved to `generated_dags/archive/` |
| `DELETE_DAG` | **BLOCKED** | Redirected to DEPRECATE_DAG with safety warning |

**AI Code Generation path** (`app/ai_code_generator.py`):
- Sends enterprise-standards prompt to nova-pro
- Pre-write gate: `ast.parse` + DAG presence + `on_failure_callback` + no hardcoded secrets
- Test generation is best-effort (timeout/failure doesn't block the DAG write)

**Jinja2 template path** (default when `USE_AI_CODE_GENERATOR=false`):
- Templates in `dag_templates/basic_dag.py.j2` and `basic_dag_test.py.j2`

---

### 5. Validation Pipeline

Three validators run in sequence (`app/validator.py`):

| Validator | Checks |
|---|---|
| `python_syntax_validator` | `ast.parse` — valid Python syntax |
| `dag_policy_validator` | Required fields: `dag_id`, `retries`, `retry_delay`, `start_date`, `schedule`, `catchup`. `catchup=False` enforced. No `datetime.now()`. |
| `security_validator` | No hardcoded passwords, tokens, private keys, AWS keys. Warns on PythonOperator usage. |

`human_review_required=True` is set whenever: validation has warnings, risk is HIGH/CRITICAL, or the DAG is AI-generated.

---

### 6. Git Workflow

All code-changing operations follow this sequence:

```
git checkout main                          # always start clean from base branch
git checkout -B feature/<ticket>-<dag_id>  # create or reset feature branch
git add generated_dags/<dag>.py            # stage only the generated DAG file
git commit -m "Add generated DAG for <ticket>"
git push -u --force origin <branch>        # force: bot-owned branches, safe
```

Feature branch naming: `feature/<ticket-id>-<dag-id>` (e.g. `feature/dagops-20-customer-transactions-dag`)

**Why `--force`**: Feature branches are exclusively bot-managed and named after ticket IDs. No human pushes to them, so `--force-with-lease`'s protection against concurrent writes is unnecessary and breaks on re-runs due to stale tracking refs after `git checkout -B`.

---

### 7. GitHub Pull Requests

| Property | Value |
|---|---|
| API version | `2022-11-28` |
| Base branch | `main` (configurable via `GITHUB_BASE_BRANCH`) |
| Draft | Always `True` for DEPRECATE_DAG, DISABLE_DAG, ARCHIVE_DAG, and AI-generated DAGs |
| Idempotent | On HTTP 422 "already exists", queries the API for the existing PR and returns it |

PR title format:
- AI-generated: `[AI-GEN][DAGOPS-20] Add DAG customer_transactions_dag`
- Destructive: `[DAGOPS-17] Deprecate DAG customer_invoice_load`

---

### 8. Jira Integration

- **Webhook inbound**: Jira Cloud → ngrok → `/webhooks/jira`
- **Comment outbound**: `POST /rest/api/3/issue/<id>/comment` (Atlassian Document Format v3)
- Comment includes: operation, risk level, validation results, PR link, AI review checklist (for AI-gen), safety warning (for DELETE redirects)

---

## Data Flow

```
1. Jira ticket created/updated
2. Webhook fires to ngrok URL
3. FastAPI receives payload, parses ADF description to plain text
4. Classifier runs keyword matching → TicketClassification
5. Bedrock Planner (if enabled) extracts structured fields → ParsedDagRequest
   └─ Bedrock operation overrides classifier (with protected exceptions)
6. Route by operation:
   ├─ READ_DAG / VALIDATE_DAG / DEBUG_DAG_FAILURE
   │   └─ run_all_validations / read_dag / debug_dag_failure
   │   └─ build_dag_ops_comment → add_jira_comment
   │   └─ return response (no git, no PR)
   └─ CREATE / MODIFY / DISABLE / DEPRECATE / ARCHIVE
       └─ dag_generator function (AI or Jinja2)
       └─ run_all_validations
       └─ create_branch_and_commit → push_branch
       └─ create_pull_request (draft)
       └─ build_dag_ops_comment → add_jira_comment
       └─ return response
```

---

## Directory Structure

```
ai-dag-ops-assistant/
├── app/
│   ├── main.py                  # FastAPI app, webhook router, 8-op handler
│   ├── models.py                # Pydantic models (OperationType, ParsedDagRequest, etc.)
│   ├── config.py                # Settings from .env
│   ├── classifier.py            # Keyword-based ticket classifier
│   ├── ticket_parser.py         # Regex-based field extractor (fallback)
│   ├── bedrock_planner.py       # AWS Bedrock nova-micro planner
│   ├── ai_code_generator.py     # AWS Bedrock nova-pro DAG code generator
│   ├── dag_generator.py         # DAG create/modify/disable/deprecate/archive
│   ├── dag_reader.py            # DAG read + debug analysis
│   ├── validator.py             # Validation orchestrator
│   ├── git_service.py           # Git branch/commit/push operations
│   ├── github_service.py        # GitHub PR creation via REST API
│   ├── jira_service.py          # Jira comment builder + poster
│   └── validators/
│       ├── __init__.py
│       ├── dag_policy_validator.py   # Required fields, catchup, start_date
│       └── security_validator.py     # Hardcoded secret detection
├── dag_templates/
│   ├── basic_dag.py.j2          # Jinja2 DAG template
│   └── basic_dag_test.py.j2     # Jinja2 test template
├── generated_dags/              # Output DAG files
│   └── archive/                 # Archived DAGs
├── generated_tests/             # Output test files
└── requirements.txt
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_TOKEN` | ✅ | — | GitHub personal access token (repo scope) |
| `GITHUB_OWNER` | ✅ | — | GitHub username / org name |
| `GITHUB_REPO` | ✅ | — | Repository name |
| `GITHUB_BASE_BRANCH` | | `main` | Base branch for PRs |
| `JIRA_BASE_URL` | ✅ | — | e.g. `https://yourorg.atlassian.net` |
| `JIRA_EMAIL` | ✅ | — | Jira account email |
| `JIRA_API_TOKEN` | ✅ | — | Jira API token |
| `AWS_REGION` | | `us-east-1` | AWS region for Bedrock |
| `BEDROCK_MODEL_ID` | | `us.amazon.nova-micro-v1:0` | Planner model |
| `BEDROCK_PROVIDER` | | `nova` | `nova` or `anthropic` |
| `USE_BEDROCK_PLANNER` | | `false` | Enable Bedrock planning |
| `USE_AI_CODE_GENERATOR` | | `false` | Enable AI DAG code generation |
| `AI_CODE_GEN_MODEL_ID` | | `us.amazon.nova-pro-v1:0` | Code gen model |
| `AI_CODE_GEN_MAX_TOKENS` | | `4000` | Max tokens for code gen (overridden per-call) |
