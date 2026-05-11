import os

from dotenv import load_dotenv


load_dotenv(override=True)


class Settings:
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    github_owner: str | None = os.getenv("GITHUB_OWNER")
    github_repo: str | None = os.getenv("GITHUB_REPO")
    github_base_branch: str = os.getenv("GITHUB_BASE_BRANCH", "main")

    jira_base_url: str | None = os.getenv("JIRA_BASE_URL")
    jira_email: str | None = os.getenv("JIRA_EMAIL")
    jira_api_token: str | None = os.getenv("JIRA_API_TOKEN")
    
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    bedrock_model_id: str = os.getenv(
    "BEDROCK_MODEL_ID",
    "us.amazon.nova-micro-v1:0",
    )
    bedrock_provider: str = os.getenv("BEDROCK_PROVIDER", "nova")
    use_bedrock_planner: bool = os.getenv("USE_BEDROCK_PLANNER", "false").lower() == "true"

settings = Settings()