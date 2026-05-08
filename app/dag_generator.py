from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.models import ParsedDagRequest


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "dag_templates"
OUTPUT_DAG_DIR = BASE_DIR / "generated_dags"
OUTPUT_TEST_DIR = BASE_DIR / "generated_tests"


def generate_dag(parsed_request: ParsedDagRequest) -> dict:
    OUTPUT_DAG_DIR.mkdir(exist_ok=True)
    OUTPUT_TEST_DIR.mkdir(exist_ok=True)

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

    dag_file = OUTPUT_DAG_DIR / f"{parsed_request.dag_id}_dag.py"
    test_file = OUTPUT_TEST_DIR / f"test_{parsed_request.dag_id}_dag.py"

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