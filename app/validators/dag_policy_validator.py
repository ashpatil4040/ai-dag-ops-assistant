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
        "dag_id": ["dag_id="],
        "owner": ['"owner"', "owner="],
        "retries": ['"retries"', "retries="],
        "retry_delay": ['"retry_delay"', "retry_delay="],
        "start_date": ["start_date="],
        "schedule": ["schedule="],
        "catchup": ["catchup="],
    }

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