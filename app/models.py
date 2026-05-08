from typing import List, Optional

from pydantic import BaseModel


class JiraTicket(BaseModel):
    ticket_id: str
    summary: str
    description: str


class TicketClassification(BaseModel):
    is_dag_related: bool
    operation: str
    risk_level: str


class ParsedDagRequest(BaseModel):
    dag_id: Optional[str] = None
    source: Optional[str] = None
    target: Optional[str] = None
    schedule: Optional[str] = None
    owner: Optional[str] = "data-platform"
    retries: int = 3
    retry_delay_minutes: int = 10
    tags: List[str] = ["ai-generated", "jira", "dag-ops"]
    missing_fields: List[str] = []
    clarification_questions: List[str] = []