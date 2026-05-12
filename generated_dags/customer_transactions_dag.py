from datetime import datetime, timedelta
from airflow import DAG
from airflow.decorators import task
from airflow.providers.amazon.aws.operators.s3_to_snowflake import S3ToSnowflakeOperator
from airflow.providers.snowflake.operators.snowflake import SnowflakeOperator
from airflow.operators.email import EmailOperator
from airflow.operators.dummy import DummyOperator
from airflow.utils.task_group import TaskGroup
from airflow.hooks.base import BaseHook

default_args = {
    'owner': 'data-engineering',
   'retries': 3,
   'retry_delay': timedelta(minutes=10),
}

def on_failure_callback(context):
    context['task_instance'].log.error("Task failed")
    email = context.get('email')
    if email:
        send_email = EmailOperator(
            task_id='send_email_on_failure',
            to=email,
            subject='Airflow Task Failed',
            html_content='Task {{ task_instance.task_id }} failed',
        )
        send_email.execute(context)

with DAG(
    dag_id='customer_transactions_dag',
    schedule_interval='0 6 * * *',
    start_date=datetime(2026, 1, 1),
    catchup=False,
    is_paused_upon_creation=False,
    default_args=default_args,
    on_failure_callback=on_failure_callback,
    tags=['ai-generated', 'jira', 'dag-ops'],
) as dag:

    doc_md = """
    ### Customer Transactions DAG
    - **Purpose**: Load customer transactions from S3 to Snowflake.
    - **Source**: `s3://finance-data-lake/customer-transactions/`
    - **Target**: `Snowflake schema FINANCE, table CUSTOMER_TRANSACTIONS`
    - **Owner**: `data-engineering`
    """

    sla_minutes = 120

    with TaskGroup(group_id='load_data') as load_data:
        s3_to_snowflake = S3ToSnowflakeOperator(
            task_id='s3_to_snowflake',
            s3_keys=['s3://finance-data-lake/customer-transactions/'],
            snowflake_conn_id='snowflake_conn',
            table='FINANCE.CUSTOMER_TRANSACTIONS',
            file_format="(format_name ='my_csv_format')",
            s3_conn_id='aws_s3_conn',
        )

    transform_data = SnowflakeOperator(
        task_id='transform_data',
        sql="CALL FINANCE.TRANSFORM_CUSTOMER_TRANSACTIONS()",
        snowflake_conn_id='snowflake_conn',
    )

    load_data.s3_to_snowflake >> transform_data