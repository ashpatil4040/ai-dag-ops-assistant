"""
dag_reader.py — Read-only DAG inspection and debug analysis.
No file writes. No git operations. Report only.
"""
import re
from pathlib import Path
from typing import Any

from app.dag_generator import find_existing_dag_file
from app.models import DebugDagResult, ReadDagResult
from app.validator import run_all_validations


def _parse_dag_metadata(code: str) -> dict[str, Any]:
    """Extract metadata fields from DAG source code via regex."""
    metadata: dict[str, Any] = {}

    # schedule
    m = re.search(r'schedule\s*=\s*["\']([^"\']*)["\']', code)
    metadata["schedule"] = m.group(1) if m else None

    # owner
    m = re.search(r'"owner"\s*:\s*["\']([^"\']+)["\']', code)
    metadata["owner"] = m.group(1) if m else None

    # retries
    m = re.search(r'"retries"\s*:\s*(\d+)', code)
    metadata["retries"] = int(m.group(1)) if m else None

    # retry_delay minutes
    m = re.search(r'timedelta\(minutes=(\d+)\)', code)
    metadata["retry_delay_minutes"] = int(m.group(1)) if m else None

    # tags  — e.g. tags=["a", "b"]
    m = re.search(r'tags\s*=\s*\[([^\]]+)\]', code)
    if m:
        metadata["tags"] = [t.strip().strip('"\'') for t in m.group(1).split(",")]
    else:
        metadata["tags"] = []

    # all task_id= values
    metadata["task_ids"] = re.findall(r'task_id\s*=\s*["\']([^"\']+)["\']', code)

    return metadata


def read_dag(dag_id: str) -> ReadDagResult:
    """
    Locate and inspect a DAG file. Returns structured metadata.
    Raises no exceptions — returns what it can find.
    """
    dag_file = find_existing_dag_file(dag_id)

    if not dag_file:
        return ReadDagResult(
            dag_id=dag_id,
            file_path="",
            raw_metadata={"error": f"DAG file not found for dag_id: {dag_id}"},
        )

    code = dag_file.read_text()
    meta = _parse_dag_metadata(code)

    return ReadDagResult(
        dag_id=dag_id,
        file_path=str(dag_file),
        schedule=meta.get("schedule"),
        owner=meta.get("owner"),
        retries=meta.get("retries"),
        retry_delay_minutes=meta.get("retry_delay_minutes"),
        tags=meta.get("tags", []),
        task_ids=meta.get("task_ids", []),
        raw_metadata=meta,
    )


def debug_dag_failure(dag_id: str, error_context: str = "") -> DebugDagResult:
    """
    Run all validations against an existing DAG and optionally invoke
    Bedrock for root-cause analysis. Returns a diagnostic report.
    """
    dag_file = find_existing_dag_file(dag_id)

    if not dag_file:
        return DebugDagResult(
            dag_id=dag_id,
            dag_found=False,
            recommendations=[f"DAG file not found for dag_id: {dag_id}. Verify the dag_id is correct."],
        )

    code = dag_file.read_text()
    meta = _parse_dag_metadata(code)
    validation = run_all_validations(str(dag_file), None)

    recommendations: list[str] = []

    if validation["errors"]:
        recommendations.append("Fix validation errors listed below before redeploying.")
    if validation["warnings"]:
        recommendations.append("Review validation warnings — they may indicate the root cause.")
    if not meta.get("schedule"):
        recommendations.append("No schedule detected — confirm the DAG is not missing its schedule.")
    if meta.get("retries", 0) == 0:
        recommendations.append("Retries are set to 0 — transient failures will not be retried.")

    # Optional Bedrock root-cause analysis
    bedrock_analysis: str | None = None
    try:
        from app.config import settings  # local import to avoid circular
        if settings.use_bedrock_planner:
            from app.bedrock_planner import invoke_bedrock_json
            debug_prompt = (
                f"You are an Airflow DAG debugging assistant.\n"
                f"DAG ID: {dag_id}\n"
                f"Error context: {error_context or 'No additional error context provided.'}\n"
                f"Validation errors: {validation['errors']}\n"
                f"Validation warnings: {validation['warnings']}\n"
                f"DAG metadata: {meta}\n\n"
                f"Provide a concise root-cause analysis and up to 3 specific fix recommendations. "
                f"Return plain text, no JSON."
            )
            # Invoke as plain text (not JSON) — wrap in try/except
            import json
            import boto3
            client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
            if settings.bedrock_provider == "nova":
                body = {
                    "messages": [{"role": "user", "content": [{"text": debug_prompt}]}],
                    "inferenceConfig": {"max_new_tokens": 600, "temperature": 0},
                }
                resp = client.invoke_model(
                    modelId=settings.bedrock_model_id,
                    body=json.dumps(body),
                    contentType="application/json",
                    accept="application/json",
                )
                rb = json.loads(resp["body"].read())
                bedrock_analysis = rb["output"]["message"]["content"][0]["text"]
            else:
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 600,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": [{"type": "text", "text": debug_prompt}]}],
                }
                resp = client.invoke_model(
                    modelId=settings.bedrock_model_id,
                    body=json.dumps(body),
                    contentType="application/json",
                    accept="application/json",
                )
                rb = json.loads(resp["body"].read())
                bedrock_analysis = rb["content"][0]["text"]
    except Exception:
        bedrock_analysis = None

    return DebugDagResult(
        dag_id=dag_id,
        dag_found=True,
        validation_results=validation,
        dag_metadata=meta,
        bedrock_analysis=bedrock_analysis,
        recommendations=recommendations,
    )
