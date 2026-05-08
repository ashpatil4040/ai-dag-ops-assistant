from fastapi import FastAPI, Request

from app.models import JiraTicket
from app.classifier import classify_ticket
from app.ticket_parser import parse_ticket
from app.dag_generator import generate_dag
from app.validator import run_all_validations
from app.git_service import create_branch_and_commit, push_branch
from app.github_service import create_pull_request


app = FastAPI(title="AI DAG Ops Assistant")


@app.get("/")
def health_check():
    return {
        "status": "running",
        "service": "AI DAG Ops Assistant",
    }


def extract_text_from_adf(value):
    """
    Jira Cloud description can come as Atlassian Document Format.
    This function extracts plain text from it.
    """
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        text_parts = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "text":
                    text_parts.append(node.get("text", ""))

                for child in node.get("content", []):
                    walk(child)

            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(value)
        return " ".join(text_parts)

    return str(value)


def normalize_jira_payload(payload: dict) -> JiraTicket:
    issue = payload.get("issue", {})
    fields = issue.get("fields", {})

    ticket_id = issue.get("key", "UNKNOWN")
    summary = fields.get("summary", "")
    description = extract_text_from_adf(fields.get("description"))

    return JiraTicket(
        ticket_id=ticket_id,
        summary=summary,
        description=description,
    )


@app.post("/webhooks/jira")
async def handle_jira_webhook(request: Request):
    payload = await request.json()

    ticket = normalize_jira_payload(payload)

    classification = classify_ticket(ticket)

    if not classification.is_dag_related:
        return {
            "ticket_id": ticket.ticket_id,
            "message": "Ticket is not DAG related",
            "classification": classification,
        }

    parsed_request = parse_ticket(ticket)

    if parsed_request.missing_fields:
        return {
            "ticket_id": ticket.ticket_id,
            "message": "Ticket is DAG related but missing required information",
            "classification": classification,
            "parsed_request": parsed_request,
            "needs_clarification": True,
            "human_review_required": True,
        }

    if classification.operation != "CREATE_DAG":
        return {
            "ticket_id": ticket.ticket_id,
            "message": "Only CREATE_DAG is supported right now",
            "classification": classification,
            "parsed_request": parsed_request,
            "human_review_required": True,
        }

    generated = generate_dag(parsed_request)

    validation = run_all_validations(
        generated["dag_file_path"],
        generated["test_file_path"],
    )

    git_result = None
    github_pr_result = None

    if validation["overall_status"] == "PASSED":
        git_result = create_branch_and_commit(
            ticket_id=ticket.ticket_id,
            dag_id=generated["dag_id"],
            file_paths=[
                generated["dag_file_path"],
                generated["test_file_path"],
            ],
        )

        if git_result and git_result.get("success"):
            push_result = push_branch(git_result["branch_name"])
            git_result["push_result"] = push_result

            if push_result.get("success"):
                github_pr_result = create_pull_request(
                    ticket_id=ticket.ticket_id,
                    dag_id=generated["dag_id"],
                    source=generated["source"],
                    target=generated["target"],
                    schedule=generated["schedule"],
                    branch_name=git_result["branch_name"],
                    validation=validation,
                )

    return {
        "ticket_id": ticket.ticket_id,
        "classification": classification,
        "parsed_request": parsed_request,
        "generated": generated,
        "validation": validation,
        "git": git_result,
        "github_pull_request": github_pr_result,
        "human_review_required": True,
    }