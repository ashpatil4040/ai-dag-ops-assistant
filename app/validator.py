import py_compile
from pathlib import Path

from app.validators.dag_policy_validator import validate_dag_policy
from app.validators.security_validator import validate_security


def validate_python_file(file_path: str) -> dict:
    path = Path(file_path)

    if not path.exists():
        return {
            "check_name": "python_syntax_validator",
            "status": "FAILED",
            "errors": [f"File does not exist: {file_path}"],
            "warnings": [],
        }

    try:
        py_compile.compile(str(path), doraise=True)
        return {
            "check_name": "python_syntax_validator",
            "status": "PASSED",
            "errors": [],
            "warnings": [],
        }
    except py_compile.PyCompileError as error:
        return {
            "check_name": "python_syntax_validator",
            "status": "FAILED",
            "errors": [str(error)],
            "warnings": [],
        }


def run_all_validations(dag_file_path: str, test_file_path: str | None = None) -> dict:
    checks = [
        validate_python_file(dag_file_path),
        validate_dag_policy(dag_file_path),
        validate_security(dag_file_path),
    ]

    if test_file_path:
        checks.append(validate_python_file(test_file_path))

    all_errors = []
    all_warnings = []

    for check in checks:
        all_errors.extend(check.get("errors", []))
        all_warnings.extend(check.get("warnings", []))

    overall_status = "PASSED" if not all_errors else "FAILED"

    return {
        "overall_status": overall_status,
        "checks": checks,
        "errors": all_errors,
        "warnings": all_warnings,
        "human_review_required": True,
    }