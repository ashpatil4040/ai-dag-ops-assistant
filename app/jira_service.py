import requests
from requests.auth import HTTPBasicAuth

from app.config import settings


def build_adf_paragraph(text: str) -> dict:
    """
    Jira Cloud API v3 expects comments in Atlassian Document Format.
    This helper creates a simple paragraph document.
    """
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": text,
                    }
                ],
            }
        ],
    }


def add_jira_comment(ticket_id: str, comment_text: str) -> dict:
    if not settings.jira_base_url:
        return {
            "success": False,
            "message": "Missing JIRA_BASE_URL in .env",
        }

    if not settings.jira_email or not settings.jira_api_token:
        return {
            "success": False,
            "message": "Missing JIRA_EMAIL or JIRA_API_TOKEN in .env",
        }

    url = f"{settings.jira_base_url}/rest/api/3/issue/{ticket_id}/comment"

    response = requests.post(
        url,
        auth=HTTPBasicAuth(settings.jira_email, settings.jira_api_token),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={
            "body": build_adf_paragraph(comment_text),
        },
        timeout=30,
    )

    if response.status_code in [200, 201]:
        data = response.json()
        return {
            "success": True,
            "comment_id": data.get("id"),
            "self": data.get("self"),
        }

    return {
        "success": False,
        "status_code": response.status_code,
        "message": response.text,
    }


def build_dag_ops_comment(
    ticket_id: str,
    generated: dict,
    validation: dict,
    git_result: dict | None,
    github_pr_result: dict | None,
) -> str:
    dag_id = generated.get("dag_id")
    source = generated.get("source")
    target = generated.get("target")
    schedule = generated.get("schedule")

    validation_status = validation.get("overall_status", "UNKNOWN")
    warnings = validation.get("warnings", [])

    branch_name = None
    if git_result:
        branch_name = git_result.get("branch_name")

    pr_url = None
    if github_pr_result and github_pr_result.get("success"):
        pr_url = github_pr_result.get("pr_url")

    warnings_text = "None"
    if warnings:
        warnings_text = "; ".join(warnings)

    pr_text = pr_url if pr_url else "PR not created yet or push failed"

    return (
        "AI DAG Ops Assistant processed this ticket.\n\n"
        f"Ticket: {ticket_id}\n"
        f"DAG ID: {dag_id}\n"
        f"Source: {source}\n"
        f"Target: {target}\n"
        f"Schedule: {schedule}\n\n"
        f"Validation: {validation_status}\n"
        f"Warnings: {warnings_text}\n\n"
        f"Git branch: {branch_name}\n"
        f"Pull request: {pr_text}\n\n"
        "Human review is required before merge or deployment."
    )