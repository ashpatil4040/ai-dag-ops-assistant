# AI DAG Ops Assistant

An AI-powered Airflow DAG operations bot. It listens for Jira tickets via webhook, understands the requested operation using keyword classification + AWS Bedrock AI planning, performs the operation (read, validate, create, modify, disable, deprecate, archive), commits generated code to a GitHub feature branch, opens a draft Pull Request, and posts results back to the Jira ticket — all automatically.

---

## Features

- **8 DAG operations** via natural language Jira tickets
- **AI-generated DAGs** using AWS Bedrock nova-pro with enterprise Airflow standards enforced
- **3-layer validation** — syntax, policy, and security checks on every generated file
- **Automated Git workflow** — feature branch → commit → push → draft PR per ticket
- **Safety guardrails** — DELETE is blocked and redirected to DEPRECATE; destructive ops always create draft PRs requiring human approval
- **Jira integration** — posts detailed operation reports with PR links back to the ticket

---

## Supported Operations

| Jira ticket says... | Operation | Risk | PR created? |
|---|---|---|---|
| "create new DAG to load..." | `CREATE_DAG` | MEDIUM | ✅ (draft if AI-generated) |
| "show me / inspect DAG..." | `READ_DAG` | LOW | ❌ |
| "modify / update DAG..." | `MODIFY_DAG` | HIGH | ✅ |
| "validate / check DAG..." | `VALIDATE_DAG` | LOW | ❌ |
| "disable / pause DAG..." | `DISABLE_DAG` | HIGH | ✅ draft |
| "deprecate / retire DAG..." | `DEPRECATE_DAG` | HIGH | ✅ draft |
| "archive DAG..." | `ARCHIVE_DAG` | CRITICAL | ✅ draft |
| "debug / broken / dag failure..." | `DEBUG_DAG_FAILURE` | MEDIUM | ❌ |
| "delete DAG..." | **BLOCKED** → `DEPRECATE_DAG` | CRITICAL | ✅ draft + safety warning |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Git configured with a user name and email
- AWS credentials with Bedrock access (`bedrock:InvokeModel` on nova-micro and nova-pro)
- A Jira Cloud project with webhook configured
- A GitHub repository

### 1. Clone and install

```bash
git clone https://github.com/<your-org>/ai-dag-ops-assistant.git
cd ai-dag-ops-assistant
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
# GitHub
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
GITHUB_OWNER=your-github-username
GITHUB_REPO=ai-dag-ops-assistant
GITHUB_BASE_BRANCH=main

# Jira Cloud
JIRA_BASE_URL=https://yourorg.atlassian.net
JIRA_EMAIL=you@yourorg.com
JIRA_API_TOKEN=your-jira-api-token

# AWS Bedrock
AWS_REGION=us-east-1
USE_BEDROCK_PLANNER=true
USE_AI_CODE_GENERATOR=true
```

### 3. Start the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### 4. Expose via ngrok (for Jira webhook)

```bash
ngrok http 8080
```

Copy the HTTPS URL (e.g. `https://abc123.ngrok-free.app`) and configure it in Jira:

> **Jira** → Project Settings → Webhooks → Create webhook
> URL: `https://abc123.ngrok-free.app/webhooks/jira`
> Events: Issue created, Issue updated

### 5. Test manually

```powershell
$body = '{"issue":{"key":"TEST-1","fields":{"summary":"create new DAG to load orders from S3 to Snowflake","description":"source: s3://data-lake/orders/, target: ORDERS table, schedule daily 6am, owner data-eng"}}}'
Invoke-RestMethod -Uri "http://localhost:8080/webhooks/jira" -Method POST -Body $body -ContentType "application/json"
```

---

## Project Structure

```
ai-dag-ops-assistant/
├── app/
│   ├── main.py                  # FastAPI app + 8-operation webhook router
│   ├── models.py                # Pydantic models
│   ├── config.py                # .env settings
│   ├── classifier.py            # Keyword-based operation classifier
│   ├── ticket_parser.py         # Regex field extractor (fallback)
│   ├── bedrock_planner.py       # AWS Bedrock nova-micro planning
│   ├── ai_code_generator.py     # AWS Bedrock nova-pro DAG code generation
│   ├── dag_generator.py         # DAG file create/modify/disable/deprecate/archive
│   ├── dag_reader.py            # DAG metadata reader + failure debugger
│   ├── validator.py             # Validation orchestrator
│   ├── git_service.py           # Git branch/commit/push
│   ├── github_service.py        # GitHub Pull Request API
│   ├── jira_service.py          # Jira comment API
│   └── validators/
│       ├── dag_policy_validator.py
│       └── security_validator.py
├── dag_templates/               # Jinja2 DAG and test templates
├── generated_dags/              # Output — committed to feature branches
│   └── archive/                 # Archived DAGs
├── generated_tests/             # Generated pytest test files
├── INFRASTRUCTURE.md            # Architecture and data flow documentation
└── requirements.txt
```

---

## How It Works

```
Jira ticket created
        │
        ▼
POST /webhooks/jira
        │
        ▼
Classifier  ──────────────►  TicketClassification
(keyword matching)           (operation, risk_level)
        │
        ▼
Bedrock Planner (nova-micro)
(extracts dag_id, source, target, schedule, etc.)
(may correct the operation — with safety exceptions)
        │
        ├─── Read-only ops ───────────────────────────────────────────────┐
        │    (READ_DAG, VALIDATE_DAG, DEBUG_DAG_FAILURE)                  │
        │    No git, no PR                                                 │
        │                                                                  ▼
        └─── Code-changing ops                                    Jira comment posted
             (CREATE, MODIFY, DISABLE, DEPRECATE, ARCHIVE)
                     │
                     ▼
             DAG Generator
             ├── AI path: Bedrock nova-pro generates enterprise-grade DAG code
             └── Template path: Jinja2 renders basic_dag.py.j2
                     │
                     ▼
             3-layer Validation
             (syntax → policy → security)
                     │
                     ▼
             Git: checkout main → create feature branch → commit → push --force
                     │
                     ▼
             GitHub: create draft Pull Request
                     │
                     ▼
             Jira: post comment with results + PR link
```

---

## Enterprise DAG Standards (AI-generated DAGs)

Every AI-generated DAG enforces:

- `on_failure_callback` wired into the `DAG()` constructor
- `doc_md` describing purpose, source, target, owner
- `catchup=False`
- `is_paused_upon_creation=False`
- `start_date=datetime(2026, 1, 1)` — never `datetime.now()`
- `sla=timedelta(minutes=120)` minimum
- `default_args` with `owner`, `retries`, `retry_delay`
- Connections via `BaseHook.get_connection()` — no hardcoded credentials
- `TaskGroup` for logically related tasks

---

## Running Tests

```bash
pytest generated_tests/ -v
```

---

## Configuration Reference

See [INFRASTRUCTURE.md](INFRASTRUCTURE.md#environment-variables) for the full environment variable reference.
