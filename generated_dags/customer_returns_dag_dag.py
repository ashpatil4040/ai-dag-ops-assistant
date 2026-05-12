from airflow import DAG
from airflow.decorators import task
from airflow.operators.email import EmailOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.providers.snowflake.operators.snowflake import SnowflakeOperator
from airflow.providers.amazon.aws.transfers.s3_to_snowflake import S3ToSnowflakeOperator
from airflow.utils.dates import days_ago
from airflow.models import Variable
from datetime import timedelta
import smtplib
from airflow.hooks.base import BaseHook

def on_failure_callback(context):
    context['task_instance'].log.error("Task failed")
    email = Variable.get("on_failure_email", default_var=None)
    if email:
        smtp_conn = BaseHook.get_connection("smtp_default")
        with smtplib.SMTP(smtp_conn.host, smtp_conn.port) as server:
            server.login(smtp_conn.login, smtp_conn.password)
            server.sendmail(smtp_conn.login, email, "Task failed")

default_args = {
   'retries': 3,
   'retry_delay': timedelta(minutes=10)
}

with DAG(
    'customer_returns_dag',
    default_args=default_args,
    description='Load customer returns data from S3 to Snowflake',
    schedule_interval='0 6 * * *',
    start_date=days_ago(1),
    catchup=False,
    is_paused_upon_creation=False,
    tags=['ai-generated', 'jira', 'dag-ops'],
    on_failure_callback=on_failure_callback
) as dag:

    @task
    def log_start():
        print("Starting customer returns DAG")

    wait_for_s3_object = S3KeySensor(
        task_id='wait_for_s3_object',
        bucket_key='customer_returns.csv',
        bucket_name='my-data-bucket',
        aws_conn_id='aws_s3_conn',
        poke_interval=60,
        timeout=600
    )

    load_to_snowflake = S3ToSnowflakeOperator(
        task_id='load_to_snowflake',
        s3_bucket='my-data-bucket',
        s3_key='customer_returns.csv',
        snowflake_conn_id='snowflake_conn',
        table='CUSTOMER_RETURNS',
        stage='my_stage',
        file_format="(format_name ='my_csv_format')",
        replace=True
    )

    transform_data = SnowflakeOperator(
        task_id='transform_data',
        sql='TRANSFORM_CUSTOMER_RETURNS.sql',
        snowflake_conn_id='snowflake_conn'
    )

    log_start() >> wait_for_s3_object >> load_to_snowflake >> transform_data