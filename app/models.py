from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class OperationType(str, Enum):
    CREATE_DAG = "CREATE_DAG"
    READ_DAG = "READ_DAG"
    MODIFY_DAG = "MODIFY_DAG"
    VALIDATE_DAG = "VALIDATE_DAG"
    DISABLE_DAG = "DISABLE_DAG"
    DEPRECATE_DAG = "DEPRECATE_DAG"
    ARCHIVE_DAG = "ARCHIVE_DAG"
    DEBUG_DAG_FAILURE = "DEBUG_DAG_FAILURE"
    UNKNOWN = "UNKNOWN"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class JiraTicket(BaseModel):
    ticket_id: str
    summary: str
    description: str


class TicketClassification(BaseModel):
    is_dag_related: bool
    operation: OperationType
    risk_level: RiskLevel
    safety_warning: Optional[str] = None


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
    # Code-gen enrichment fields
    pipeline_type: Optional[str] = None
    connection_ids: Optional[Dict[str, str]] = None
    on_failure_email: Optional[str] = None
    sla_minutes: Optional[int] = None
    task_groups: Optional[List[str]] = None
    ai_generated_code: Optional[str] = None


class ReadDagResult(BaseModel):
    dag_id: str
    file_path: str
    schedule: Optional[str] = None
    owner: Optional[str] = None
    retries: Optional[int] = None
    retry_delay_minutes: Optional[int] = None
    tags: List[str] = []
    task_ids: List[str] = []
    raw_metadata: Dict[str, Any] = {}


class DisableDagResult(BaseModel):
    success: bool
    dag_id: str
    dag_file_path: Optional[str] = None
    test_file_path: Optional[str] = None
    change_type: str = "DISABLE_DAG"
    message: Optional[str] = None


class DeprecateDagResult(BaseModel):
    success: bool
    dag_id: str
    dag_file_path: Optional[str] = None
    change_type: str = "DEPRECATE_DAG"
    message: Optional[str] = None


class ArchiveDagResult(BaseModel):
    success: bool
    dag_id: str
    archive_path: Optional[str] = None
    original_path: Optional[str] = None
    change_type: str = "ARCHIVE_DAG"
    message: Optional[str] = None


class DebugDagResult(BaseModel):
    dag_id: str
    dag_found: bool
    validation_results: Optional[Dict[str, Any]] = None
    dag_metadata: Optional[Dict[str, Any]] = None
    bedrock_analysis: Optional[str] = None
    recommendations: List[str] = []