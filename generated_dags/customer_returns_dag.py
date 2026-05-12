from airflow import DAG
from airflow.decorators import task
from airflow.operators.email import EmailOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.providers.snowflake.operators.snowflake import SnowflakeOperator
from airflow.providers.amazon.aws.transfers.s3_to_snowflake import S3ToSnowflakeOperator
from airflow.utils.dates import days_ago
from airflow.models import Variable
from datetime import timedelta
from airflow.hooks.base import BaseHook
import smtplib
from email.mime.text import MIMEText
import logging

def on_failure_callback(context):
    logging.error("Task failed: %s", context['task_instance'])
    email_address = Variable.get("on_failure_email", default_var=None)
    if email_address:
        msg = MIMEText(f"Task {context['task_instance'].task_id} failed")
        msg['Subject'] = f"Airflow Task Failed: {context['task_instance'].task_id}"
        msg['From'] = "airflow@example.com"
        msg['To'] = email_address
        with smtplib.SMTP('localhost') as server:
            server.send_message(msg)

default_args = {
   'retries': 3,
   'retry_delay': timedelta(minutes=10),
}

with DAG(
    dag_id='customer_returns_dag',
    default_args=default_args,
    description='Process customer returns data from S3 to Snowflake',
    schedule_interval='0 6 * * *',
    start_date=days_ago(1),
    catchup=False,
    is_paused_upon_creation=False,
    tags=['ai-generated', 'jira', 'dag-ops'],
    on_failure_callback=on_failure_callback,
    user_defined_macros=dict(sla=timedelta(minutes=120)),
    doc_md="""
    ### Customer Returns DAG
    - **Purpose**: Process customer returns data.
    - **Source**: `s3://my-data-bucket/`
    - **Target**: `FINANCE`
    - **Owner**: `data-eng`
    """
) as dag:

    @task
    def extract():
        conn = BaseHook.get_connection("aws_s3_conn")
        return conn.host

    wait_for_s3_object = S3KeySensor(
        task_id='wait_for_s3_object',
        bucket_key='customer_returns.csv',
        bucket_name='my-data-bucket',
        aws_conn_id='aws_s3_conn',
        poke_interval=60,
        timeout=600,
    )

    load_to_snowflake = S3ToSnowflakeOperator(
        task_id='load_to_snowflake',
        s3_bucket='my-data-bucket',
        s3_key='customer_returns.csv',
        snowflake_conn_id='snowflake_conn',
        table_name='CUSTOMER_RETURNS',
        file_format="(format_name ='my_csv_format')",
        stage='my_stage',
    )

    transform_data = SnowflakeOperator(
        task_id='transform_data',
        sql="SELECT * FROM CUSTOMER_RETURNS WHERE return_date > CURRENT_DATE - INTERVAL '1 month'",
        snowflake_conn_id='snowflake_conn',
    )

    extract() >> wait_for_s3_object >> load_to_snowflake >> transform_data