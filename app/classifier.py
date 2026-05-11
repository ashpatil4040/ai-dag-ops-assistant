from app.models import JiraTicket, TicketClassification


def classify_ticket(ticket: JiraTicket) -> TicketClassification:
    text = f"{ticket.summary} {ticket.description}".lower()

    dag_keywords = ["dag", "airflow", "schedule", "task", "pipeline"]

    is_dag_related = any(keyword in text for keyword in dag_keywords)

    if not is_dag_related:
        return TicketClassification(
            is_dag_related=False,
            operation="UNKNOWN",
            risk_level="LOW",
        )

    if "disable" in text or "pause" in text:
        operation = "DISABLE_DAG"
        risk_level = "HIGH"
    elif "modify" in text or "update" in text or "change" in text:
        operation = "MODIFY_DAG"
        risk_level = "HIGH"
    elif "create" in text or "new dag" in text:
        operation = "CREATE_DAG"
        risk_level = "MEDIUM"
    elif "validate" in text or "check" in text:
        operation = "VALIDATE_DAG"
        risk_level = "LOW"
    else:
        operation = "UNKNOWN"
        risk_level = "MEDIUM"

    return TicketClassification(
        is_dag_related=True,
        operation=operation,
        risk_level=risk_level,
    )