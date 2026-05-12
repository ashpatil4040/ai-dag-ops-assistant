from pathlib import Path


def validate_dag_policy(file_path: str) -> dict:
    path = Path(file_path)

    if not path.exists():
        return {
            "check_name": "dag_policy_validator",
            "status": "FAILED",
            "errors": [f"File does not exist: {file_path}"],
            "warnings": [],
        }

    code = path.read_text()

    errors = []
    warnings = []

    required_patterns = {
        # dag_id: positional arg DAG('id', ...) or keyword dag_id='id'
        "dag_id": ["dag_id=", "DAG("],
        # retries: dict key (single or double quotes) or keyword arg
        "retries": ['"retries"', "'retries'", "retries="],
        # retry_delay: dict key (single or double quotes) or keyword arg
        "retry_delay": ['"retry_delay"', "'retry_delay'", "retry_delay="],
        "start_date": ["start_date="],
        # schedule: Airflow 2.4+ param or legacy schedule_interval
        "schedule": ["schedule=", "schedule_interval="],
        "catchup": ["catchup="],
    }

    # owner is best-practice but Airflow defaults to "airflow" if absent —
    # flag as a warning so AI-generated DAGs that put owner in doc_md still pass.
    _owner_patterns = ['"owner"', "'owner'", "owner="]
    if not any(p in code for p in _owner_patterns):
        warnings.append("Missing recommended DAG field: owner (add to default_args or DAG constructor)")

    for field, patterns in required_patterns.items():
        if not any(p in code for p in patterns):
            errors.append(f"Missing required DAG field: {field}")

    if "catchup=False" not in code.replace(" ", ""):
        errors.append("DAG must explicitly set catchup=False")

    if "datetime.now()" in code:
        errors.append("Do not use datetime.now() for DAG start_date")

    if "start_date=datetime" not in code:
        warnings.append("Start date should be a fixed datetime value")

    if "retries" in code and '"retries": 0' in code:
        warnings.append("Retries are set to 0. Production DAGs should usually retry transient failures.")

    return {
        "check_name": "dag_policy_validator",
        "status": "PASSED" if not errors else "FAILED",
        "errors": errors,
        "warnings": warnings,
    }