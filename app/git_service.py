import re
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def run_git_command(args: list[str]) -> dict:
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=True,
        )

        return {
            "success": True,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    except subprocess.CalledProcessError as error:
        return {
            "success": False,
            "stdout": error.stdout.strip() if error.stdout else "",
            "stderr": error.stderr.strip() if error.stderr else str(error),
        }


def normalize_branch_part(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value


def build_branch_name(ticket_id: str, dag_id: str) -> str:
    ticket_part = normalize_branch_part(ticket_id)
    dag_part = normalize_branch_part(dag_id)

    return f"feature/{ticket_part}-{dag_part}"


def ensure_git_repo() -> dict:
    result = run_git_command(["rev-parse", "--is-inside-work-tree"])

    if not result["success"]:
        return {
            "success": False,
            "message": "This project folder is not a Git repository. Run: git init",
            "details": result,
        }

    return {
        "success": True,
        "message": "Git repository detected",
    }


def create_or_checkout_branch(branch_name: str) -> dict:
    existing_branch = run_git_command(["branch", "--list", branch_name])

    if existing_branch["success"] and existing_branch["stdout"]:
        checkout_result = run_git_command(["checkout", branch_name])
        return {
            "success": checkout_result["success"],
            "action": "checked_out_existing_branch",
            "branch_name": branch_name,
            "details": checkout_result,
        }

    create_result = run_git_command(["checkout", "-b", branch_name])

    return {
        "success": create_result["success"],
        "action": "created_new_branch",
        "branch_name": branch_name,
        "details": create_result,
    }


def stage_files(file_paths: list[str]) -> dict:
    relative_paths = []

    for file_path in file_paths:
        path = Path(file_path).resolve()
        relative_path = path.relative_to(BASE_DIR)
        relative_paths.append(str(relative_path))

    result = run_git_command(["add"] + relative_paths)

    return {
        "success": result["success"],
        "staged_files": relative_paths,
        "details": result,
    }


def has_staged_changes() -> bool:
    result = run_git_command(["diff", "--cached", "--name-only"])

    if not result["success"]:
        return False

    return bool(result["stdout"].strip())


def commit_files(commit_message: str) -> dict:
    if not has_staged_changes():
        return {
            "success": False,
            "commit_created": False,
            "message": "No staged changes to commit",
        }

    result = run_git_command(["commit", "-m", commit_message])

    return {
        "success": result["success"],
        "commit_created": result["success"],
        "commit_message": commit_message,
        "details": result,
    }


def create_branch_and_commit(
    ticket_id: str,
    dag_id: str,
    file_paths: list[str],
) -> dict:
    repo_check = ensure_git_repo()

    if not repo_check["success"]:
        return {
            "success": False,
            "stage": "repo_check",
            "repo_check": repo_check,
        }

    branch_name = build_branch_name(ticket_id, dag_id)

    branch_result = create_or_checkout_branch(branch_name)

    if not branch_result["success"]:
        return {
            "success": False,
            "stage": "branch",
            "branch_name": branch_name,
            "branch_result": branch_result,
        }

    stage_result = stage_files(file_paths)

    if not stage_result["success"]:
        return {
            "success": False,
            "stage": "stage_files",
            "branch_name": branch_name,
            "stage_result": stage_result,
        }

    commit_message = f"Add generated DAG for {ticket_id}"

    commit_result = commit_files(commit_message)

    return {
        "success": commit_result["success"],
        "branch_name": branch_name,
        "commit_message": commit_message,
        "commit_created": commit_result.get("commit_created", False),
        "branch_result": branch_result,
        "stage_result": stage_result,
        "commit_result": commit_result,
    }