"""
ai_code_generator.py — Enterprise-grade Airflow DAG code generation via AWS Bedrock.
Separated from bedrock_planner.py (planning != code generation).
"""
import ast
import json
import re
from typing import Any

import boto3

from app.config import settings
from app.models import ParsedDagRequest
from app.validators.security_validator import DANGEROUS_PATTERNS


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

_ENTERPRISE_STANDARDS = """
ENTERPRISE AIRFLOW DAG STANDARDS (must be applied to every DAG):

1. on_failure_callback: Every DAG must define an on_failure_callback that sends an alert email.
   Use a local function that calls context['task_instance'].log.error() and, if an email address
   is available, uses EmailOperator or smtplib to notify.

2. doc_md: Every DAG must have a doc_md docstring describing its purpose, source, target and owner.

3. SLA: Define sla=timedelta(minutes=<N>) on at least the main data-loading task.

4. Connection IDs: Never hardcode credentials. Retrieve connections via:
       from airflow.hooks.base import BaseHook
       conn = BaseHook.get_connection("<connection_id>")
   Use well-known connection ID conventions: aws_s3_conn, snowflake_conn, http_default.

5. catchup=False: Always set catchup=False.

6. is_paused_upon_creation=False: Always set is_paused_upon_creation=False.

7. start_date: Always use datetime(2026, 1, 1) — never datetime.now().

8. TaskGroup: Group logically related tasks (e.g., extract, transform, load) using TaskGroup.

9. No hardcoded secrets: No passwords, tokens, access keys or private keys in source code.

10. Retry policy: Set retries and retry_delay in default_args.
"""

_OPERATOR_GUIDE = """
OPERATOR SELECTION GUIDE:

- S3 → Snowflake pipeline: Use S3ToSnowflakeOperator (provider: apache-airflow-providers-snowflake)
- Snowflake SQL transform: Use SnowflakeOperator
- Wait for S3 object: Use S3KeySensor (provider: apache-airflow-providers-amazon)
- HTTP API call: Use SimpleHttpOperator
- Custom Python logic: Use @task decorator (TaskFlow API) — preferred over PythonOperator
- File sensor: Use FileSensor
- Branch logic: Use BranchPythonOperator or @task.branch
"""


def build_code_gen_prompt(parsed_request: ParsedDagRequest) -> str:
    spec = {
        "dag_id": parsed_request.dag_id,
        "source": parsed_request.source,
        "target": parsed_request.target,
        "schedule": parsed_request.schedule,
        "owner": parsed_request.owner,
        "retries": parsed_request.retries,
        "retry_delay_minutes": parsed_request.retry_delay_minutes,
        "tags": parsed_request.tags,
        "pipeline_type": parsed_request.pipeline_type,
        "connection_ids": parsed_request.connection_ids,
        "on_failure_email": parsed_request.on_failure_email,
        "sla_minutes": parsed_request.sla_minutes,
        "task_groups": parsed_request.task_groups,
    }

    return f"""You are an expert Airflow DAG engineer at a large enterprise company.

{_ENTERPRISE_STANDARDS}

{_OPERATOR_GUIDE}

TASK:
Write a complete, production-ready Airflow DAG Python file for the following specification:

{json.dumps(spec, indent=2)}

REQUIREMENTS:
- The DAG must be complete and immediately runnable — no TODOs, no placeholder comments.
- Include all necessary imports at the top.
- Apply all enterprise standards listed above without exception.
- Use the most appropriate Airflow operator for the pipeline type.
- The file must end with the dag variable assigned at module level so Airflow can discover it.
- Infer the pipeline_type from source and target if pipeline_type is null.
- If connection_ids is null, use sensible defaults (aws_s3_conn, snowflake_conn).
- If on_failure_email is null, log the failure to the task logger only.
- If sla_minutes is null, set SLA to 120 minutes.

OUTPUT FORMAT:
Return ONLY valid Python source code.
Do NOT wrap in markdown code fences.
Do NOT include any explanation, prose, or comments outside the code itself.
""".strip()


def build_code_gen_test_prompt(parsed_request: ParsedDagRequest, dag_code: str) -> str:
    return f"""You are a senior data engineer writing pytest tests for an Airflow DAG.

DAG specification:
  dag_id: {parsed_request.dag_id}
  schedule: {parsed_request.schedule}
  retries: {parsed_request.retries}

The following is the complete generated DAG source code:

{dag_code}

TASK:
Write a complete pytest test file for the DAG above.

REQUIREMENTS:
- Import the dag object from the generated module: from generated_dags.{parsed_request.dag_id}_dag import dag
- Test that the dag object is importable and has the correct dag_id.
- Test that catchup is False.
- Test that retries matches the spec.
- Test that every task_id found in the code is present in dag.task_ids.
- Test that on_failure_callback is set on the DAG.
- Test that the SLA is set on at least one task (check task.sla is not None for any task).
- Test the full dependency chain using task.downstream_task_ids or dag.get_task().
- Use pytest fixtures where appropriate.
- Do NOT use unittest — use plain pytest functions.

OUTPUT FORMAT:
Return ONLY valid Python source code.
Do NOT wrap in markdown code fences.
Do NOT include any explanation or prose outside the code.
""".strip()


# ---------------------------------------------------------------------------
# Bedrock invocation (code-gen specific — uses ai_code_gen_model_id and max_tokens)
# ---------------------------------------------------------------------------

def _invoke_bedrock_text(prompt: str) -> str:
    """Invoke Bedrock and return raw text (not parsed JSON)."""
    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    model_id = settings.ai_code_gen_model_id
    max_tokens = settings.ai_code_gen_max_tokens
    provider = settings.bedrock_provider

    if provider == "nova":
        body: dict[str, Any] = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"max_new_tokens": max_tokens, "temperature": 0},
        }
    else:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        }

    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    response_body = json.loads(response["body"].read())

    if provider == "nova":
        return response_body["output"]["message"]["content"][0]["text"]
    return response_body["content"][0]["text"]


def _strip_markdown_fences(text: str) -> str:
    """Safety net: strip ```python ... ``` or ``` ... ``` wrappers if model adds them."""
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text.strip())
    return text.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_dag_code(parsed_request: ParsedDagRequest) -> str:
    prompt = build_code_gen_prompt(parsed_request)
    raw = _invoke_bedrock_text(prompt)
    return _strip_markdown_fences(raw)


def generate_test_code(parsed_request: ParsedDagRequest, dag_code: str) -> str:
    prompt = build_code_gen_test_prompt(parsed_request, dag_code)
    raw = _invoke_bedrock_text(prompt)
    return _strip_markdown_fences(raw)


def validate_generated_code_structure(code_str: str) -> dict[str, Any]:
    """
    Pre-write safety gate. Checks:
      1. Valid Python syntax (ast.parse)
      2. Contains DAG( — is actually an Airflow DAG
      3. Contains on_failure_callback — enterprise standard enforced
      4. Contains catchup=False
      5. No dangerous credential patterns (re-uses security_validator list)
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Syntax check
    try:
        ast.parse(code_str)
    except SyntaxError as exc:
        errors.append(f"Syntax error in generated code: {exc}")
        # Cannot proceed with content checks if unparseable
        return {"valid": False, "errors": errors, "warnings": warnings}

    # 2. DAG presence
    if "DAG(" not in code_str:
        errors.append("Generated code does not contain a DAG() constructor.")

    # 3. on_failure_callback
    if "on_failure_callback" not in code_str:
        errors.append("Generated code is missing on_failure_callback — enterprise standard requires it.")

    # 4. catchup=False
    if "catchup=False" not in code_str:
        warnings.append("catchup=False not found — verify the DAG will not backfill unintentionally.")

    # 5. Security patterns
    lower_code = code_str.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in lower_code:
            errors.append(f"Security: potential hardcoded credential pattern found: '{pattern}'")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
