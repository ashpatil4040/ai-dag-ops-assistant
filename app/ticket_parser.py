import re

from app.models import JiraTicket, ParsedDagRequest


def normalize_dag_id(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def extract_dag_id(text: str, summary: str) -> str:
    patterns = [
        r"dag named ([a-zA-Z0-9_]+)",
        r"dag name[:\s]+([a-zA-Z0-9_]+)",
        r"dag_id[:\s]+([a-zA-Z0-9_]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return normalize_dag_id(match.group(1))

    return normalize_dag_id(summary)


def extract_source(text: str) -> str | None:
    patterns = [
        r"source is ([^\.\n]+)",
        r"source[:\s]+([^\.\n]+)",
        r"from (s3://[^\s\.\n]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def extract_target(text: str) -> str | None:
    patterns = [
        r"target is ([^\.\n]+)",
        r"target[:\s]+([^\.\n]+)",
        r"to snowflake table ([a-zA-Z0-9_\.]+)",
        r"snowflake table ([a-zA-Z0-9_\.]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def extract_schedule(text: str) -> str | None:
    lower_text = text.lower()

    if "2 am" in lower_text or "2:00 am" in lower_text:
        return "0 2 * * *"

    if "daily" in lower_text:
        return "0 0 * * *"

    if "hourly" in lower_text:
        return "0 * * * *"

    if "every 6 hours" in lower_text:
        return "0 */6 * * *"

    if "weekly" in lower_text:
        return "0 0 * * 0"

    cron_match = re.search(r"cron[:\s]+([0-9\*/,\-\s]+)", text, re.IGNORECASE)
    if cron_match:
        return cron_match.group(1).strip()

    return None


def extract_owner(text: str) -> str:
    patterns = [
        r"owner should be ([a-zA-Z0-9_\-]+)",
        r"owner[:\s]+([a-zA-Z0-9_\-]+)",
        r"team[:\s]+([a-zA-Z0-9_\-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return "data-platform"


def extract_retries(text: str) -> int:
    patterns = [
        r"retries should be (\d+)",
        r"retries[:\s]+(\d+)",
        r"retry (\d+) times",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return 3


def extract_retry_delay(text: str) -> int:
    patterns = [
        r"retry delay should be (\d+) minutes",
        r"retry_delay[:\s]+(\d+)",
        r"retry delay[:\s]+(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return 10


def build_clarification_questions(missing_fields: list[str]) -> list[str]:
    questions = []

    if "source" in missing_fields:
        questions.append("What is the source system or source path for this DAG?")

    if "target" in missing_fields:
        questions.append("What is the target system, table, bucket, or destination?")

    if "schedule" in missing_fields:
        questions.append("What schedule should this DAG run on? For example, daily at 2 AM, hourly, weekly, or a cron expression.")

    return questions


def parse_ticket(ticket: JiraTicket) -> ParsedDagRequest:
    text = f"{ticket.summary}. {ticket.description}"

    dag_id = extract_dag_id(text, ticket.summary)
    source = extract_source(text)
    target = extract_target(text)
    schedule = extract_schedule(text)
    owner = extract_owner(text)
    retries = extract_retries(text)
    retry_delay_minutes = extract_retry_delay(text)

    missing_fields = []

    if not source:
        missing_fields.append("source")

    if not target:
        missing_fields.append("target")

    if not schedule:
        missing_fields.append("schedule")

    clarification_questions = build_clarification_questions(missing_fields)

    return ParsedDagRequest(
        dag_id=dag_id,
        source=source,
        target=target,
        schedule=schedule,
        owner=owner,
        retries=retries,
        retry_delay_minutes=retry_delay_minutes,
        missing_fields=missing_fields,
        clarification_questions=clarification_questions,
    )