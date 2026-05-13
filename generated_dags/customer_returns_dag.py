from datetime import datetime, timedelta
from airflow import DAG
from airflow.decorators import task
from airflow.operators.email import EmailOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.providers.snowflake.operators.snowflake import SnowflakeOperator
from airflow.providers.amazon.aws.transfers.s3_to_snowflake import S3ToSnowflakeOperator
from airflow.hooks.base import BaseHook

default_args = {
   'retries': 3,
   'retry_delay': timedelta(minutes=10)
}

def on_failure_callback(context):
    task_instance = context['task_instance']
    task_instance.log.error("Task failed")
    if context.get('on_failure_email'):
        EmailOperator(
            task_id='send_failure_email',
            to=context['on_failure_email'],
            subject='Airflow Task Failed',
            html_content='Task {{ task_instance.task_id }} failed',
        ).execute(context)

conn = BaseHook.get_connection("aws_s3_conn")
s3_conn_id = conn.conn_id
conn = BaseHook.get_connection("snowflake_conn")
snowflake_conn_id = conn.conn_id

with DAG(
    'customer_returns_dag',
    default_args=default_args,
    description='Load customer returns data from S3 to Snowflake',
    schedule_interval='0 6 * * *',
    start_date=datetime(2026, 1, 1),
    catchup=False,
    is_paused_upon_creation=False,
    tags=['ai-generated', 'jira', 'dag-ops'],
    sla=timedelta(minutes=120),
    doc_md="""
    ### DAG Purpose
    Load customer returns data from S3 to Snowflake.

    ### Source
    `s3://my-data-bucket/`

    ### Target
    `FINANCE`

    ### Owner
    `data-eng`
    """,
    on_failure_callback=on_failure_callback
) as dag:

    @task
    def extract():
        return "s3://my-data-bucket/customer_returns.csv"

    wait_for_s3_object = S3KeySensor(
        task_id='wait_for_s3_object',
        bucket_key='customer_returns.csv',
        bucket_name='my-data-bucket',
        aws_conn_id=s3_conn_id,
        poke_interval=60,
        timeout=600
    )

    load_to_snowflake = S3ToSnowflakeOperator(
        task_id='load_to_snowflake',
        s3_keys=['customer_returns.csv'],
        stage="my_stage",
        schema="public",
        table="customer_returns",
        file_format="(format_name ='my_csv_format')",
        snowflake_conn_id=snowflake_conn_id,
    )

    transform_data = SnowflakeOperator(
        task_id='transform_data',
        sql="SELECT * FROM customer_returns WHERE return_date > CURRENT_DATE - INTERVAL '1 month'",
        snowflake_conn_id=snowflake_conn_id
    )

    wait_for_s3_object >> extract() >> load_to_snowflake >> transform_data