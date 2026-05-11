import os

from dotenv import load_dotenv


load_dotenv()


class Settings:
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    github_owner: str | None = os.getenv("GITHUB_OWNER")
    github_repo: str | None = os.getenv("GITHUB_REPO")
    github_base_branch: str = os.getenv("GITHUB_BASE_BRANCH", "main")

    jira_base_url: str | None = os.getenv("JIRA_BASE_URL")
    jira_email: str | None = os.getenv("JIRA_EMAIL")
    jira_api_token: str | None = os.getenv("JIRA_API_TOKEN")


settings = Settings()