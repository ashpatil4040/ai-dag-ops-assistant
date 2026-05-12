from app.models import JiraTicket, OperationType, RiskLevel, TicketClassification


def classify_ticket(ticket: JiraTicket) -> TicketClassification:
    text = f"{ticket.summary} {ticket.description}".lower()

    dag_keywords = ["dag", "airflow", "schedule", "task", "pipeline"]
    is_dag_related = any(keyword in text for keyword in dag_keywords)

    if not is_dag_related:
        return TicketClassification(
            is_dag_related=False,
            operation=OperationType.UNKNOWN,
            risk_level=RiskLevel.LOW,
        )

    # DELETE is blocked — redirect to DEPRECATE with CRITICAL risk and a warning
    if "delete" in text:
        return TicketClassification(
            is_dag_related=True,
            operation=OperationType.DEPRECATE_DAG,
            risk_level=RiskLevel.CRITICAL,
            safety_warning=(
                "DELETE_DAG is blocked in this system. "
                "The request has been automatically redirected to DEPRECATE_DAG. "
                "A human must review and approve before any action is taken."
            ),
        )

    if "archive" in text:
        return TicketClassification(
            is_dag_related=True,
            operation=OperationType.ARCHIVE_DAG,
            risk_level=RiskLevel.CRITICAL,
        )

    if "disable" in text or "pause" in text:
        return TicketClassification(
            is_dag_related=True,
            operation=OperationType.DISABLE_DAG,
            risk_level=RiskLevel.HIGH,
        )

    if any(kw in text for kw in ["deprecate", "sunset", "retire", "decommission"]):
        return TicketClassification(
            is_dag_related=True,
            operation=OperationType.DEPRECATE_DAG,
            risk_level=RiskLevel.HIGH,
        )

    if any(kw in text for kw in ["debug", "failure", "failed", "broken", "investigate", "why did", "error in dag"]):
        return TicketClassification(
            is_dag_related=True,
            operation=OperationType.DEBUG_DAG_FAILURE,
            risk_level=RiskLevel.MEDIUM,
        )

    if any(kw in text for kw in ["show me", "what does", "inspect", "describe", "what is", "list tasks"]):
        return TicketClassification(
            is_dag_related=True,
            operation=OperationType.READ_DAG,
            risk_level=RiskLevel.LOW,
        )

    if any(kw in text for kw in ["modify", "update", "change"]):
        return TicketClassification(
            is_dag_related=True,
            operation=OperationType.MODIFY_DAG,
            risk_level=RiskLevel.HIGH,
        )

    if "create" in text or "new dag" in text:
        return TicketClassification(
            is_dag_related=True,
            operation=OperationType.CREATE_DAG,
            risk_level=RiskLevel.MEDIUM,
        )

    if any(kw in text for kw in ["validate", "check"]):
        return TicketClassification(
            is_dag_related=True,
            operation=OperationType.VALIDATE_DAG,
            risk_level=RiskLevel.LOW,
        )

    return TicketClassification(
        is_dag_related=True,
        operation=OperationType.UNKNOWN,
        risk_level=RiskLevel.MEDIUM,
    )