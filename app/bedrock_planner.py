import json
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings
from app.models import JiraTicket, ParsedDagRequest


def build_planner_prompt(ticket: JiraTicket) -> str:
    return f"""
You are an enterprise Airflow DAG operations planner.

Read the Jira ticket and return ONLY valid JSON.
Do not include markdown.
Do not include explanations outside JSON.

Allowed operations:
- CREATE_DAG
- MODIFY_DAG
- DISABLE_DAG
- VALIDATE_DAG
- UNKNOWN

Rules:
- If source, target, or schedule is missing, set needs_clarification=true.
- Do not invent source or target values.
- Convert common schedules into cron.
- Daily at 2 AM means "0 2 * * *".
- Hourly means "0 * * * *".
- Every 6 hours means "0 */6 * * *".
- Default owner is "data-platform".
- Default retries is 3.
- Default retry_delay_minutes is 10.
- Always require human review.
- Risk is MEDIUM for create DAG.
- Risk is HIGH for modify, disable, delete, production connection, target table, or schedule changes.

Return JSON with this exact shape:
{{
  "operation": "CREATE_DAG",
  "dag_id": "example_dag",
  "source": "s3://example/path/",
  "target": "Snowflake table EXAMPLE_TABLE",
  "schedule": "0 2 * * *",
  "owner": "data-platform",
  "retries": 3,
  "retry_delay_minutes": 10,
  "risk_level": "MEDIUM",
  "needs_clarification": false,
  "clarification_questions": [],
  "implementation_plan": []
}}

Jira ticket:
Ticket ID: {ticket.ticket_id}
Summary: {ticket.summary}
Description: {ticket.description}
""".strip()


def invoke_bedrock_json(prompt: str) -> dict[str, Any]:
    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

    print("Using Bedrock model/profile:", settings.bedrock_model_id)
    print("Using AWS region:", settings.aws_region)
    print("Using Bedrock provider:", settings.bedrock_provider)

    if settings.bedrock_provider == "nova":
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": prompt
                        }
                    ],
                }
            ],
            "inferenceConfig": {
                "max_new_tokens": 1200,
                "temperature": 0,
            },
        }

    else:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1200,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        }
                    ],
                }
            ],
        }

    response = client.invoke_model(
        modelId=settings.bedrock_model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    response_body = json.loads(response["body"].read())

    if settings.bedrock_provider == "nova":
        text = response_body["output"]["message"]["content"][0]["text"]
    else:
        text = response_body["content"][0]["text"]

    return json.loads(text)

def bedrock_plan_ticket(ticket: JiraTicket) -> dict[str, Any]:
    prompt = build_planner_prompt(ticket)

    try:
        plan = invoke_bedrock_json(prompt)
        return {
            "success": True,
            "planner": "bedrock",
            "plan": plan,
            "error": None,
        }
    except (BotoCoreError, ClientError, json.JSONDecodeError, KeyError) as error:
        return {
            "success": False,
            "planner": "bedrock",
            "plan": None,
            "error": str(error),
        }


def convert_bedrock_plan_to_parsed_request(plan: dict[str, Any]) -> ParsedDagRequest:
    missing_fields = []

    if not plan.get("source"):
        missing_fields.append("source")

    if not plan.get("target"):
        missing_fields.append("target")

    if not plan.get("schedule"):
        missing_fields.append("schedule")

    clarification_questions = plan.get("clarification_questions", [])

    return ParsedDagRequest(
        dag_id=plan.get("dag_id"),
        source=plan.get("source"),
        target=plan.get("target"),
        schedule=plan.get("schedule"),
        owner=plan.get("owner", "data-platform"),
        retries=int(plan.get("retries", 3)),
        retry_delay_minutes=int(plan.get("retry_delay_minutes", 10)),
        tags=["ai-generated", "jira", "dag-ops"],
        missing_fields=missing_fields,
        clarification_questions=clarification_questions,
    )