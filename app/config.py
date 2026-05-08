import os

from dotenv import load_dotenv


load_dotenv()


class Settings:
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    github_owner: str | None = os.getenv("GITHUB_OWNER")
    github_repo: str | None = os.getenv("GITHUB_REPO")
    github_base_branch: str = os.getenv("GITHUB_BASE_BRANCH", "main")


settings = Settings()