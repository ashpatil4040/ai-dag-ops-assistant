from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.models import JiraTicket, OperationType
from app.classifier import classify_ticket
from app.ticket_parser import parse_ticket
from app.dag_generator import generate_dag, modify_existing_dag, disable_dag, deprecate_dag, archive_dag
from app.dag_reader import read_dag, debug_dag_failure
from app.validator import run_all_validations
from app.git_service import create_branch_and_commit, push_branch
from app.github_service import create_pull_request
from app.jira_service import add_jira_comment, build_dag_ops_comment
from app.config import settings
from app.bedrock_planner import bedrock_plan_ticket, convert_bedrock_plan_to_parsed_request


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

    # Hard block: DELETE_DAG should never reach here (classifier redirects),
    # but guard defensively at the router level too.
    if str(classification.operation) == "DELETE_DAG":
        return JSONResponse(
            status_code=400,
            content={
                "ticket_id": ticket.ticket_id,
                "error": "DELETE_DAG is blocked in this system.",
                "redirected_to": "DEPRECATE_DAG",
                "message": "Use DEPRECATE_DAG, DISABLE_DAG, or ARCHIVE_DAG instead.",
            },
        )

    # -----------------------------------------------------------------------
    # READ-ONLY operations — no git, no PR, report only
    # -----------------------------------------------------------------------

    if classification.operation == OperationType.READ_DAG:
        _ro_parsed = convert_bedrock_plan_to_parsed_request(
            bedrock_plan_ticket(ticket)["plan"]
        ) if settings.use_bedrock_planner else parse_ticket(ticket)
        dag_id = _ro_parsed.dag_id or ticket.summary.split()[-1]
        result = read_dag(dag_id)
        report_dict = result.model_dump()

        comment_text = build_dag_ops_comment(
            ticket_id=ticket.ticket_id,
            generated={**report_dict, "source": None, "target": None, "schedule": result.schedule},
            validation={"overall_status": "N/A", "errors": [], "warnings": []},
            git_result=None,
            github_pr_result=None,
            operation="READ_DAG",
            risk_level="LOW",
        )
        add_jira_comment(ticket_id=ticket.ticket_id, comment_text=comment_text)

        return {
            "ticket_id": ticket.ticket_id,
            "classification": classification,
            "operation": "READ_DAG",
            "read_result": report_dict,
            "git": None,
            "github_pull_request": None,
            "human_review_required": False,
        }

    if classification.operation == OperationType.VALIDATE_DAG:
        _ro_parsed = convert_bedrock_plan_to_parsed_request(
            bedrock_plan_ticket(ticket)["plan"]
        ) if settings.use_bedrock_planner else parse_ticket(ticket)
        dag_id = _ro_parsed.dag_id or ticket.summary.split()[-1]
        from app.dag_generator import find_existing_dag_file
        dag_file = find_existing_dag_file(dag_id)

        if not dag_file:
            return {
                "ticket_id": ticket.ticket_id,
                "operation": "VALIDATE_DAG",
                "message": f"DAG file not found for dag_id: {dag_id}",
                "human_review_required": True,
            }

        validation = run_all_validations(str(dag_file), None)
        comment_text = build_dag_ops_comment(
            ticket_id=ticket.ticket_id,
            generated={"dag_id": dag_id, "source": None, "target": None, "schedule": None},
            validation=validation,
            git_result=None,
            github_pr_result=None,
            operation="VALIDATE_DAG",
            risk_level="LOW",
        )
        add_jira_comment(ticket_id=ticket.ticket_id, comment_text=comment_text)

        return {
            "ticket_id": ticket.ticket_id,
            "classification": classification,
            "operation": "VALIDATE_DAG",
            "dag_id": dag_id,
            "validation": validation,
            "git": None,
            "github_pull_request": None,
            "human_review_required": False,
        }

    if classification.operation == OperationType.DEBUG_DAG_FAILURE:
        _ro_parsed = convert_bedrock_plan_to_parsed_request(
            bedrock_plan_ticket(ticket)["plan"]
        ) if settings.use_bedrock_planner else parse_ticket(ticket)
        dag_id = _ro_parsed.dag_id or ticket.summary.split()[-1]
        error_context = ticket.description

        debug_result = debug_dag_failure(dag_id, error_context)
        result_dict = debug_result.model_dump()

        comment_text = build_dag_ops_comment(
            ticket_id=ticket.ticket_id,
            generated={
                "dag_id": dag_id,
                "source": None,
                "target": None,
                "schedule": None,
                "task_ids": debug_result.dag_metadata.get("task_ids", []) if debug_result.dag_metadata else [],
                "bedrock_analysis": debug_result.bedrock_analysis,
                "recommendations": debug_result.recommendations,
            },
            validation=debug_result.validation_results or {"overall_status": "UNKNOWN", "errors": [], "warnings": []},
            git_result=None,
            github_pr_result=None,
            operation="DEBUG_DAG_FAILURE",
            risk_level="MEDIUM",
        )
        add_jira_comment(ticket_id=ticket.ticket_id, comment_text=comment_text)

        return {
            "ticket_id": ticket.ticket_id,
            "classification": classification,
            "operation": "DEBUG_DAG_FAILURE",
            "debug_result": result_dict,
            "git": None,
            "github_pull_request": None,
            "human_review_required": False,
        }

    # -----------------------------------------------------------------------
    # Code-modifying operations — require parsed_request
    # -----------------------------------------------------------------------

    bedrock_planner_result = None

    if settings.use_bedrock_planner:
        bedrock_planner_result = bedrock_plan_ticket(ticket)
        if bedrock_planner_result["success"]:
            parsed_request = convert_bedrock_plan_to_parsed_request(bedrock_planner_result["plan"])
            # Override classifier's operation and risk_level with Bedrock's more context-aware detection.
            # Exceptions (classifier wins, Bedrock cannot override):
            #   1. DELETE→DEPRECATE safety redirect (safety-critical)
            #   2. ARCHIVE_DAG — "archive" keyword is unambiguous; Bedrock can misread descriptions
            #      that mention "deprecated for 90 days" when the actual intent is archival.
            bedrock_op_str = bedrock_planner_result["plan"].get("operation", "")
            bedrock_risk_str = bedrock_planner_result["plan"].get("risk_level", "")
            is_delete_redirect = classification.safety_warning and "DELETE_DAG" in classification.safety_warning
            is_protected_op = classification.operation == OperationType.ARCHIVE_DAG
            should_override = bedrock_op_str and not is_delete_redirect and not is_protected_op
            updates = {}
            if should_override:
                try:
                    updates["operation"] = OperationType(bedrock_op_str)
                except ValueError:
                    pass
                if bedrock_risk_str:
                    try:
                        from app.models import RiskLevel
                        updates["risk_level"] = RiskLevel(bedrock_risk_str)
                    except ValueError:
                        pass
            elif not is_delete_redirect and not is_protected_op and bedrock_risk_str:
                # Still allow Bedrock to upgrade risk_level even when op is protected
                try:
                    from app.models import RiskLevel
                    updates["risk_level"] = RiskLevel(bedrock_risk_str)
                except ValueError:
                    pass
            if updates:
                classification = classification.model_copy(update=updates)
        else:
            parsed_request = parse_ticket(ticket)
    else:
        parsed_request = parse_ticket(ticket)

    # For destructive ops (DISABLE/DEPRECATE/ARCHIVE) missing_fields are not blockers —
    # we only need dag_id. For CREATE/MODIFY we need the full spec.
    destructive_ops = {
        OperationType.DISABLE_DAG,
        OperationType.DEPRECATE_DAG,
        OperationType.ARCHIVE_DAG,
    }
    if classification.operation not in destructive_ops and parsed_request.missing_fields:
        return {
            "ticket_id": ticket.ticket_id,
            "message": "Ticket is DAG related but missing required information",
            "classification": classification,
            "parsed_request": parsed_request,
            "bedrock_planner": bedrock_planner_result,
            "needs_clarification": True,
            "human_review_required": True,
        }

    # Route to the correct generator / modifier
    if classification.operation == OperationType.CREATE_DAG:
        generated = generate_dag(parsed_request)

    elif classification.operation == OperationType.MODIFY_DAG:
        generated = modify_existing_dag(parsed_request)
        if not generated.get("success"):
            return {
                "ticket_id": ticket.ticket_id,
                "message": generated.get("message"),
                "classification": classification,
                "parsed_request": parsed_request,
                "bedrock_planner": bedrock_planner_result,
                "human_review_required": True,
            }

    elif classification.operation == OperationType.DISABLE_DAG:
        generated = disable_dag(parsed_request)
        if not generated.get("success"):
            return {
                "ticket_id": ticket.ticket_id,
                "message": generated.get("message"),
                "classification": classification,
                "human_review_required": True,
            }

    elif classification.operation == OperationType.DEPRECATE_DAG:
        generated = deprecate_dag(parsed_request, ticket_id=ticket.ticket_id)
        if not generated.get("success"):
            return {
                "ticket_id": ticket.ticket_id,
                "message": generated.get("message"),
                "classification": classification,
                "safety_warning": classification.safety_warning,
                "human_review_required": True,
            }

    elif classification.operation == OperationType.ARCHIVE_DAG:
        generated = archive_dag(parsed_request, ticket_id=ticket.ticket_id)
        if not generated.get("success"):
            return {
                "ticket_id": ticket.ticket_id,
                "message": generated.get("message"),
                "classification": classification,
                "human_review_required": True,
            }

    else:
        return {
            "ticket_id": ticket.ticket_id,
            "message": f"{classification.operation} is not supported yet",
            "classification": classification,
            "parsed_request": parsed_request,
            "bedrock_planner": bedrock_planner_result,
            "human_review_required": True,
        }

    # -----------------------------------------------------------------------
    # Validation → git → PR → Jira (shared path for all code-modifying ops)
    # -----------------------------------------------------------------------

    dag_file_path = generated.get("dag_file_path")
    test_file_path = generated.get("test_file_path")

    # For AI_GENERATED the pre-write gate already ran; run full validations anyway
    validation = run_all_validations(dag_file_path, test_file_path)

    # AI_GENERATED code failures: still create PR so engineer can review
    # For template ops: block PR on validation failure
    change_type = generated.get("change_type", "")
    ai_generated = change_type == "AI_GENERATED"

    git_result = None
    github_pr_result = None

    if validation["overall_status"] == "PASSED" or ai_generated:
        git_result = create_branch_and_commit(
            ticket_id=ticket.ticket_id,
            dag_id=generated["dag_id"],
            file_paths=[p for p in [dag_file_path, test_file_path] if p],
        )

        if git_result and git_result.get("success"):
            push_result = push_branch(git_result["branch_name"])
            git_result["push_result"] = push_result

            if push_result.get("success"):
                github_pr_result = create_pull_request(
                    ticket_id=ticket.ticket_id,
                    dag_id=generated["dag_id"],
                    source=generated.get("source") or "",
                    target=generated.get("target") or "",
                    schedule=generated.get("schedule") or "",
                    branch_name=git_result["branch_name"],
                    validation=validation,
                    operation=str(classification.operation.value),
                    risk_level=str(classification.risk_level.value),
                    safety_warning=classification.safety_warning,
                    ai_generated=ai_generated,
                    ai_model=generated.get("ai_model"),
                )

    comment_text = build_dag_ops_comment(
        ticket_id=ticket.ticket_id,
        generated=generated,
        validation=validation,
        git_result=git_result,
        github_pr_result=github_pr_result,
        operation=str(classification.operation.value),
        risk_level=str(classification.risk_level.value),
        safety_warning=classification.safety_warning,
    )
    jira_comment_result = add_jira_comment(
        ticket_id=ticket.ticket_id,
        comment_text=comment_text,
    )

    return {
        "ticket_id": ticket.ticket_id,
        "classification": classification,
        "parsed_request": parsed_request,
        "bedrock_planner": bedrock_planner_result,
        "generated": generated,
        "validation": validation,
        "git": git_result,
        "github_pull_request": github_pr_result,
        "jira_comment": jira_comment_result,
        "safety_warning": classification.safety_warning,
        "human_review_required": True,
    }