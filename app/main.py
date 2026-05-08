from fastapi import FastAPI

from app.models import JiraTicket
from app.classifier import classify_ticket
from app.ticket_parser import parse_ticket
from app.dag_generator import generate_dag
from app.validator import run_all_validations
from app.git_service import create_branch_and_commit


app = FastAPI(title="AI DAG Ops Assistant")


@app.get("/")
def health_check():
    return {
        "status": "running",
        "service": "AI DAG Ops Assistant",
    }


@app.post("/webhooks/jira")
def handle_jira_ticket(ticket: JiraTicket):
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

    if validation["overall_status"] == "PASSED":
        git_result = create_branch_and_commit(
            ticket_id=ticket.ticket_id,
            dag_id=generated["dag_id"],
            file_paths=[
                generated["dag_file_path"],
                generated["test_file_path"],
            ],
        )

    return {
        "ticket_id": ticket.ticket_id,
        "classification": classification,
        "parsed_request": parsed_request,
        "generated": generated,
        "validation": validation,
        "git": git_result,
        "human_review_required": True,
    }