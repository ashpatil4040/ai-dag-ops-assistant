from pathlib import Path


DANGEROUS_PATTERNS = [
    "password=",
    "password =",
    "secret=",
    "secret =",
    "access_key=",
    "access_key =",
    "aws_access_key_id",
    "aws_secret_access_key",
    "private_key",
    "token=",
    "token =",
    "rm -rf",
    "sudo ",
    "chmod 777",
]


def validate_security(file_path: str) -> dict:
    path = Path(file_path)

    if not path.exists():
        return {
            "check_name": "security_validator",
            "status": "FAILED",
            "errors": [f"File does not exist: {file_path}"],
            "warnings": [],
        }

    code = path.read_text().lower()

    errors = []
    warnings = []

    for pattern in DANGEROUS_PATTERNS:
        if pattern in code:
            errors.append(f"Potential unsafe or secret-related pattern found: {pattern}")

    if "bashoperator" in code:
        warnings.append("BashOperator detected. Review command safety before approving.")

    if "pythonoperator" in code:
        warnings.append("PythonOperator detected. Review callable logic before approving.")

    return {
        "check_name": "security_validator",
        "status": "PASSED" if not errors else "FAILED",
        "errors": errors,
        "warnings": warnings,
    }