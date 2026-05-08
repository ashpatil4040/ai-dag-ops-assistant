import importlib.util
from pathlib import Path


DAG_FILE = Path(__file__).resolve().parent.parent / "generated_dags" / "customer_chargeback_load_dag.py"


def load_dag_module():
    spec = importlib.util.spec_from_file_location("customer_chargeback_load_dag", DAG_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dag_file_exists():
    assert DAG_FILE.exists()


def test_dag_imports_successfully():
    module = load_dag_module()
    assert module is not None
    assert hasattr(module, "dag")


def test_dag_id_is_correct():
    module = load_dag_module()
    assert module.dag.dag_id == "customer_chargeback_load"


def test_expected_tasks_exist():
    module = load_dag_module()
    task_ids = [task.task_id for task in module.dag.tasks]

    expected_tasks = [
        "start",
        "check_source_available",
        "load_to_target",
        "validate_load",
        "end",
    ]

    for task_id in expected_tasks:
        assert task_id in task_ids


def test_schedule_is_correct():
    module = load_dag_module()
    assert str(module.dag.schedule_interval) == "0 2 * * *" or str(module.dag.timetable.summary) == "0 2 * * *"
    

def test_catchup_is_false():
    module = load_dag_module()
    assert module.dag.catchup is False


def test_retries_are_configured():
    module = load_dag_module()
    retries = module.dag.default_args.get("retries")
    assert retries == 3


def test_task_dependency_order():
    module = load_dag_module()

    start = module.dag.get_task("start")
    check_source = module.dag.get_task("check_source_available")
    load = module.dag.get_task("load_to_target")
    validate = module.dag.get_task("validate_load")
    end = module.dag.get_task("end")

    assert check_source.task_id in start.downstream_task_ids
    assert load.task_id in check_source.downstream_task_ids
    assert validate.task_id in load.downstream_task_ids
    assert end.task_id in validate.downstream_task_ids