from datetime import date
from pathlib import Path
import re
from jinja2 import Environment, FileSystemLoader
from app.models import ParsedDagRequest


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "dag_templates"
OUTPUT_DAG_DIR = BASE_DIR / "generated_dags"
OUTPUT_TEST_DIR = BASE_DIR / "generated_tests"
ARCHIVE_DIR = OUTPUT_DAG_DIR / "archive"


def generate_dag(parsed_request: ParsedDagRequest) -> dict:
    OUTPUT_DAG_DIR.mkdir(exist_ok=True)
    OUTPUT_TEST_DIR.mkdir(exist_ok=True)

    # --- AI Code Generator path ---
    from app.config import settings  # local import avoids circular at module level
    if settings.use_ai_code_generator:
        from app.ai_code_generator import (
            generate_dag_code,
            generate_test_code,
            validate_generated_code_structure,
        )

        dag_code = generate_dag_code(parsed_request)
        code_validation = validate_generated_code_structure(dag_code)

        if not code_validation["valid"]:
            return {
                "success": False,
                "dag_id": parsed_request.dag_id,
                "message": "AI-generated DAG code failed pre-write validation.",
                "code_validation": code_validation,
            }

        test_code = generate_test_code(parsed_request, dag_code)
        test_validation = validate_generated_code_structure(test_code)

        dag_stem = parsed_request.dag_id if parsed_request.dag_id.endswith("_dag") else f"{parsed_request.dag_id}_dag"
        dag_file = OUTPUT_DAG_DIR / f"{dag_stem}.py"
        test_file = OUTPUT_TEST_DIR / f"test_{dag_stem}.py"

        dag_file.write_text(dag_code)
        if test_validation["valid"]:
            test_file.write_text(test_code)

        return {
            "dag_id": parsed_request.dag_id,
            "source": parsed_request.source,
            "target": parsed_request.target,
            "schedule": parsed_request.schedule,
            "dag_file_path": str(dag_file),
            "test_file_path": str(test_file) if test_validation["valid"] else None,
            "change_type": "AI_GENERATED",
            "code_validation": code_validation,
            "ai_model": settings.ai_code_gen_model_id,
        }

    # --- Jinja2 template path (default, backward-compatible) ---
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

    dag_template = env.get_template("basic_dag.py.j2")
    test_template = env.get_template("basic_dag_test.py.j2")

    rendered_dag_code = dag_template.render(
        dag_id=parsed_request.dag_id,
        source=parsed_request.source,
        target=parsed_request.target,
        owner=parsed_request.owner,
        retries=parsed_request.retries,
        retry_delay_minutes=parsed_request.retry_delay_minutes,
        schedule=parsed_request.schedule,
        tags=parsed_request.tags,
    )

    rendered_test_code = test_template.render(
        dag_id=parsed_request.dag_id,
        schedule=parsed_request.schedule,
        retries=parsed_request.retries,
    )

    dag_stem = parsed_request.dag_id if parsed_request.dag_id.endswith("_dag") else f"{parsed_request.dag_id}_dag"
    dag_file = OUTPUT_DAG_DIR / f"{dag_stem}.py"
    test_file = OUTPUT_TEST_DIR / f"test_{dag_stem}.py"

    dag_file.write_text(rendered_dag_code)
    test_file.write_text(rendered_test_code)

    return {
        "dag_id": parsed_request.dag_id,
        "source": parsed_request.source,
        "target": parsed_request.target,
        "schedule": parsed_request.schedule,
        "dag_file_path": str(dag_file),
        "test_file_path": str(test_file),
    }

def find_existing_dag_file(dag_id: str) -> Path | None:
    possible_file = OUTPUT_DAG_DIR / f"{dag_id}_dag.py"

    if possible_file.exists():
        return possible_file

    for file in OUTPUT_DAG_DIR.glob("*_dag.py"):
        content = file.read_text()
        if f'dag_id="{dag_id}"' in content or f"dag_id='{dag_id}'" in content:
            return file

    return None


def modify_existing_dag(parsed_request: ParsedDagRequest) -> dict:
    OUTPUT_DAG_DIR.mkdir(exist_ok=True)
    OUTPUT_TEST_DIR.mkdir(exist_ok=True)

    dag_file = find_existing_dag_file(parsed_request.dag_id)

    if not dag_file:
        return {
            "success": False,
            "message": f"Existing DAG file not found for dag_id: {parsed_request.dag_id}",
            "dag_id": parsed_request.dag_id,
        }

    code = dag_file.read_text()

    if parsed_request.schedule:
        code = re.sub(
            r'schedule="[^"]+"',
            f'schedule="{parsed_request.schedule}"',
            code,
        )

    if parsed_request.retries is not None:
        code = re.sub(
            r'"retries":\s*\d+',
            f'"retries": {parsed_request.retries}',
            code,
        )

    if parsed_request.retry_delay_minutes is not None:
        code = re.sub(
            r"retry_delay\":\s*timedelta\(minutes=\d+\)",
            f'retry_delay": timedelta(minutes={parsed_request.retry_delay_minutes})',
            code,
        )

    dag_file.write_text(code)

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    test_template = env.get_template("basic_dag_test.py.j2")

    rendered_test_code = test_template.render(
        dag_id=parsed_request.dag_id,
        schedule=parsed_request.schedule,
        retries=parsed_request.retries,
    )

    test_file = OUTPUT_TEST_DIR / f"test_{parsed_request.dag_id}_dag.py"
    test_file.write_text(rendered_test_code)

    return {
        "success": True,
        "dag_id": parsed_request.dag_id,
        "source": parsed_request.source,
        "target": parsed_request.target,
        "schedule": parsed_request.schedule,
        "dag_file_path": str(dag_file),
        "test_file_path": str(test_file),
        "change_type": "MODIFY_DAG",
    }


def disable_dag(parsed_request: ParsedDagRequest) -> dict:
    """
    Disable an existing DAG by setting schedule=None and
    is_paused_upon_creation=True. Regenerates the test file.
    Risk: HIGH — always requires human review via PR.
    """
    OUTPUT_DAG_DIR.mkdir(exist_ok=True)
    OUTPUT_TEST_DIR.mkdir(exist_ok=True)

    dag_file = find_existing_dag_file(parsed_request.dag_id)
    if not dag_file:
        return {
            "success": False,
            "dag_id": parsed_request.dag_id,
            "message": f"DAG file not found for dag_id: {parsed_request.dag_id}",
            "change_type": "DISABLE_DAG",
        }

    code = dag_file.read_text()

    # Set schedule to None
    code = re.sub(r'schedule\s*=\s*["\'][^"\']*["\']', "schedule=None", code)
    # Also handle schedule=None already present (idempotent)

    # Add or update is_paused_upon_creation
    if "is_paused_upon_creation" in code:
        code = re.sub(
            r"is_paused_upon_creation\s*=\s*(True|False)",
            "is_paused_upon_creation=True",
            code,
        )
    else:
        # Inject after catchup=False if present, else after schedule=None
        code = re.sub(
            r"(catchup\s*=\s*False)",
            r"\1,\n    is_paused_upon_creation=True",
            code,
            count=1,
        )

    dag_file.write_text(code)

    # Regenerate test file
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    test_template = env.get_template("basic_dag_test.py.j2")
    rendered_test_code = test_template.render(
        dag_id=parsed_request.dag_id,
        schedule=None,
        retries=parsed_request.retries,
    )
    test_file = OUTPUT_TEST_DIR / f"test_{parsed_request.dag_id}_dag.py"
    test_file.write_text(rendered_test_code)

    return {
        "success": True,
        "dag_id": parsed_request.dag_id,
        "dag_file_path": str(dag_file),
        "test_file_path": str(test_file),
        "change_type": "DISABLE_DAG",
    }


def deprecate_dag(parsed_request: ParsedDagRequest, ticket_id: str = "") -> dict:
    """
    Mark an existing DAG as deprecated by:
    - Prepending a DEPRECATED header comment block
    - Appending "deprecated" to the tags list
    - Setting schedule=None

    Risk: HIGH — always requires human review via PR.
    """
    OUTPUT_DAG_DIR.mkdir(exist_ok=True)

    dag_file = find_existing_dag_file(parsed_request.dag_id)
    if not dag_file:
        return {
            "success": False,
            "dag_id": parsed_request.dag_id,
            "message": f"DAG file not found for dag_id: {parsed_request.dag_id}",
            "change_type": "DEPRECATE_DAG",
        }

    code = dag_file.read_text()

    deprecation_header = (
        f"# =============================================================================\n"
        f"# DEPRECATED: {date.today().isoformat()}\n"
        f"# Ticket: {ticket_id or 'N/A'}\n"
        f"# This DAG has been deprecated and should not be re-enabled without approval.\n"
        f"# =============================================================================\n\n"
    )

    # Only prepend if not already deprecated
    if "# DEPRECATED:" not in code:
        code = deprecation_header + code

    # Append "deprecated" to tags list if not already present
    if '"deprecated"' not in code and "'deprecated'" not in code:
        code = re.sub(
            r'(tags\s*=\s*\[)([^\]]*)\]',
            lambda m: m.group(1) + m.group(2).rstrip() + ', "deprecated"]',
            code,
            count=1,
        )

    # Set schedule to None
    code = re.sub(r'schedule\s*=\s*["\'][^"\']*["\']', "schedule=None", code)

    dag_file.write_text(code)

    return {
        "success": True,
        "dag_id": parsed_request.dag_id,
        "dag_file_path": str(dag_file),
        "change_type": "DEPRECATE_DAG",
    }


def archive_dag(parsed_request: ParsedDagRequest, ticket_id: str = "") -> dict:
    """
    Archive an existing DAG by:
    - Copying the original file to generated_dags/archive/
    - Adding an ARCHIVED header to the original (preserves diff in PR)

    Risk: CRITICAL — always requires human review via PR.
    """
    OUTPUT_DAG_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)

    dag_file = find_existing_dag_file(parsed_request.dag_id)
    if not dag_file:
        return {
            "success": False,
            "dag_id": parsed_request.dag_id,
            "message": f"DAG file not found for dag_id: {parsed_request.dag_id}",
            "change_type": "ARCHIVE_DAG",
        }

    code = dag_file.read_text()

    # Write clean copy to archive
    archive_file = ARCHIVE_DIR / dag_file.name
    archive_file.write_text(code)

    # Mark original with ARCHIVED header
    archive_header = (
        f"# =============================================================================\n"
        f"# ARCHIVED: {date.today().isoformat()}\n"
        f"# Ticket: {ticket_id or 'N/A'}\n"
        f"# Original archived to: generated_dags/archive/{dag_file.name}\n"
        f"# This file should be removed after PR is approved and merged.\n"
        f"# =============================================================================\n\n"
    )
    if "# ARCHIVED:" not in code:
        dag_file.write_text(archive_header + code)

    return {
        "success": True,
        "dag_id": parsed_request.dag_id,
        "dag_file_path": str(dag_file),
        "archive_path": str(archive_file),
        "change_type": "ARCHIVE_DAG",
    }