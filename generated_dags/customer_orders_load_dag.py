from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.standard.operators.python import PythonOperator


default_args = {
    "owner": "data-platform",
    "retries": 3,
    "retry_delay": timedelta(minutes=10),
}


def check_source_available(**context):
    source = "s3://raw/orders/"
    print(f"Checking source availability: {source}")
    return True


def load_to_target(**context):
    source = "s3://raw/orders/"
    target = "Snowflake table CUSTOMER_ORDERS"
    print(f"Loading data from {source} to {target}")
    return {
        "source": source,
        "target": target,
        "status": "loaded",
    }


def validate_load(**context):
    target = "Snowflake table CUSTOMER_ORDERS"
    print(f"Validating load for target: {target}")
    return True


with DAG(
    dag_id="customer_orders_load",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    is_paused_upon_creation=True,
    tags=['ai-generated', 'jira', 'dag-ops'],
) as dag:

    start = EmptyOperator(task_id="start")

    check_source = PythonOperator(
        task_id="check_source_available",
        python_callable=check_source_available,
    )

    load = PythonOperator(
        task_id="load_to_target",
        python_callable=load_to_target,
    )

    validate = PythonOperator(
        task_id="validate_load",
        python_callable=validate_load,
    )

    end = EmptyOperator(task_id="end")

    start >> check_source >> load >> validate >> end