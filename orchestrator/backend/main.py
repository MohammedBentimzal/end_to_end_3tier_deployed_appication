import asyncio
import os
import re
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator


BASE_DIR = Path(__file__).resolve().parent.parent
TERRAFORM_DIR = Path(os.getenv("TERRAFORM_DIR", BASE_DIR / "infra" / "terraform")).resolve()
ANSIBLE_DIR = Path(os.getenv("ANSIBLE_DIR", BASE_DIR / "infra" / "ansible")).resolve()
INVENTORY_FILE = os.getenv("ANSIBLE_INVENTORY", "inventory.aws_ec2.yaml")
ANSIBLE_PLAYBOOK = os.getenv("ANSIBLE_PLAYBOOK", "site.yaml")
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

# SSH private key used by the SSH agent
SSH_KEY = os.getenv(
    "SSH_KEY",
    "/home/mohammed/Downloads/flask_app.pem"
)


ALLOWED_BACKENDS = {"django", "gin"}
ALLOWED_DATABASES = {"postgres", "mysql", "mongo"}
ENV_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,39}$")


app = FastAPI(title="Self-Service Platform API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


state_lock = threading.Lock()

state: dict[str, Any] = {
    "job_id": None,
    "status": "idle",
    "message": "Choose your stack and environment.",
    "environment": None,
    "backend": None,
    "database": None,
    "application": None,
    "logs": [],
    "error": None,
}


class DeployRequest(BaseModel):
    backend: str
    database: str
    env_name: str = Field(min_length=1, max_length=40)

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, value: str) -> str:
        if value not in ALLOWED_BACKENDS:
            raise ValueError(
                f"backend must be one of: {', '.join(sorted(ALLOWED_BACKENDS))}"
            )
        return value

    @field_validator("database")
    @classmethod
    def validate_database(cls, value: str) -> str:
        if value not in ALLOWED_DATABASES:
            raise ValueError(
                f"database must be one of: {', '.join(sorted(ALLOWED_DATABASES))}"
            )
        return value

    @field_validator("env_name")
    @classmethod
    def validate_env_name(cls, value: str) -> str:
        if not ENV_NAME_RE.fullmatch(value):
            raise ValueError(
                "Use 1-40 characters: letters, numbers, '-' or '_'."
            )
        return value


class DestroyRequest(BaseModel):
    backend: str
    database: str
    env_name: str


def snapshot() -> dict[str, Any]:
    with state_lock:
        return dict(state)


def set_state(**values: Any) -> None:
    with state_lock:
        state.update(values)


def add_log(text: str) -> None:
    with state_lock:
        state["logs"].append(text)
        state["logs"] = state["logs"][-200:]


# ============================================================
# SSH AGENT
# ============================================================

def setup_ssh_agent() -> dict[str, str]:
    """
    Start ssh-agent and add the SSH private key.

    Equivalent to:

        eval "$(ssh-agent -s)"
        ssh-add /home/mohammed/Downloads/flask_app.pem
    """

    if not Path(SSH_KEY).exists():
        raise RuntimeError(
            f"SSH private key does not exist: {SSH_KEY}"
        )

    add_log("Starting SSH agent...")

    result = subprocess.run(
        ["ssh-agent", "-s"],
        capture_output=True,
        text=True,
        check=True,
    )

    env = os.environ.copy()

    # Parse:
    #
    # SSH_AUTH_SOCK=/tmp/ssh-XXXX/agent.1234; export SSH_AUTH_SOCK;
    # SSH_AGENT_PID=1234; export SSH_AGENT_PID;

    for line in result.stdout.splitlines():

        if line.startswith("SSH_AUTH_SOCK="):
            env["SSH_AUTH_SOCK"] = (
                line.split("=", 1)[1]
                .split(";", 1)[0]
            )

        elif line.startswith("SSH_AGENT_PID="):
            env["SSH_AGENT_PID"] = (
                line.split("=", 1)[1]
                .split(";", 1)[0]
            )

    if "SSH_AUTH_SOCK" not in env:
        raise RuntimeError(
            "Could not get SSH_AUTH_SOCK from ssh-agent."
        )

    if "SSH_AGENT_PID" not in env:
        raise RuntimeError(
            "Could not get SSH_AGENT_PID from ssh-agent."
        )

    add_log(
        f"SSH agent started: PID {env['SSH_AGENT_PID']}"
    )

    add_result = subprocess.run(
        ["ssh-add", SSH_KEY],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    if add_result.stdout:
        for line in add_result.stdout.splitlines():
            add_log(line)

    if add_result.stderr:
        for line in add_result.stderr.splitlines():
            add_log(f"[ssh-add] {line}")

    if add_result.returncode != 0:
        raise RuntimeError(
            f"ssh-add failed with exit code "
            f"{add_result.returncode}"
        )

    add_log("SSH key added to SSH agent.")

    # Verify that the key is actually loaded.
    list_result = subprocess.run(
        ["ssh-add", "-l"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    if list_result.stdout:
        for line in list_result.stdout.splitlines():
            add_log(f"[ssh-agent] {line}")

    return env


def stop_ssh_agent(env: dict[str, str]) -> None:
    """Stop the SSH agent created for this deployment."""

    try:
        subprocess.run(
            ["ssh-agent", "-k"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        add_log("SSH agent stopped.")

    except Exception as exc:
        add_log(
            f"[warning] Could not stop SSH agent: {exc}"
        )


# ============================================================
# COMMAND EXECUTION
# ============================================================

def run_command(
    args: list[str],
    cwd: Path,
    label: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one CLI command and wait until it finishes.

    Because deployment runs in a background thread, this blocking
    subprocess.run() does not block FastAPI's main event loop.
    """

    command = " ".join(args)

    add_log(f"$ {command}")

    if env is None:
        env = os.environ.copy()

    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    if result.stdout:
        for line in result.stdout.splitlines():
            add_log(line)

    if result.stderr:
        for line in result.stderr.splitlines():
            add_log(f"[stderr] {line}")

    add_log(
        f"{label} finished with exit code {result.returncode}"
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed with exit code "
            f"{result.returncode}"
        )

    return result


def ensure_workspace(
    env_name: str,
    env: dict[str, str] | None = None,
) -> None:
    """Select an existing workspace, or create it when it does not exist."""

    if env is None:
        env = os.environ.copy()

    selected = subprocess.run(
        ["terraform", "workspace", "select", env_name],
        cwd=str(TERRAFORM_DIR),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    if selected.returncode == 0:
        add_log(
            f"Terraform workspace '{env_name}' selected."
        )
        return

    run_command(
        [
            "terraform",
            "workspace",
            "new",
            env_name,
        ],
        TERRAFORM_DIR,
        "terraform workspace new",
        env,
    )

    run_command(
        [
            "terraform",
            "workspace",
            "select",
            env_name,
        ],
        TERRAFORM_DIR,
        "terraform workspace select",
        env,
    )


def get_public_ip(
    env: dict[str, str] | None = None,
) -> str | None:

    if env is None:
        env = os.environ.copy()

    result = subprocess.run(
        [
            "terraform",
            "output",
            "-raw",
            "public_ip",
        ],
        cwd=str(TERRAFORM_DIR),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    if result.returncode == 0:

        value = result.stdout.strip()

        if value:
            return value

    # Fallback if the Terraform output is named `application` instead.
    result = subprocess.run(
        [
            "terraform",
            "output",
            "-raw",
            "application",
        ],
        cwd=str(TERRAFORM_DIR),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    return None


# ============================================================
# DEPLOYMENT
# ============================================================

def deploy_sync(
    request: DeployRequest,
    job_id: str,
) -> None:

    ssh_env = None

    try:

        if not DEMO_MODE:

            if not TERRAFORM_DIR.exists():
                raise RuntimeError(
                    f"Terraform directory does not exist: "
                    f"{TERRAFORM_DIR}"
                )

            if not ANSIBLE_DIR.exists():
                raise RuntimeError(
                    f"Ansible directory does not exist: "
                    f"{ANSIBLE_DIR}"
                )

            # ------------------------------------------------
            # START SSH AGENT
            # ------------------------------------------------

            ssh_env = setup_ssh_agent()

            # ------------------------------------------------
            # TERRAFORM INIT
            # ------------------------------------------------

            set_state(
                status="deploying",
                message="Initializing Terraform...",
                error=None,
            )

            run_command(
                [
                    "terraform",
                    "init",
                ],
                TERRAFORM_DIR,
                "terraform init",
                ssh_env,
            )

            # ------------------------------------------------
            # TERRAFORM WORKSPACE
            # ------------------------------------------------

            set_state(
                message=(
                    f"Selecting Terraform workspace "
                    f"'{request.env_name}'..."
                )
            )

            ensure_workspace(
                request.env_name,
                ssh_env,
            )

            # ------------------------------------------------
            # TERRAFORM APPLY
            # ------------------------------------------------

            set_state(
                message=(
                    "Terraform is provisioning "
                    "the infrastructure..."
                )
            )

            run_command(
                [
                    "terraform",
                    "apply",
                    "-auto-approve",
                    f"-var=backend={request.backend}",
                    f"-var=database={request.database}",
                    f"-var=env_name={request.env_name}",
                ],
                TERRAFORM_DIR,
                "terraform apply",
                ssh_env,
            )

            # ------------------------------------------------
            # GET PUBLIC IP
            # ------------------------------------------------

            application = get_public_ip(ssh_env)

            if not application:
                raise RuntimeError(
                    "Terraform finished, but no public IP was found. "
                    "Add a Terraform output named 'public_ip'."
                )

            set_state(
                application=application,
                message=(
                    "Terraform finished. "
                    "Running Ansible..."
                ),
            )

            # ------------------------------------------------
            # ANSIBLE
            # ------------------------------------------------

            run_command(
                [
                    "ansible-playbook",
                    "-i",
                    INVENTORY_FILE,
                    ANSIBLE_PLAYBOOK,
                    "-e",
                    f"backend_type={request.backend}",
                    "-e",
                    f"db_engine={request.database}",
                    "-e",
                    f"env_name={request.env_name}",
                    "--limit",
                    request.env_name,
                ],
                ANSIBLE_DIR,
                "ansible-playbook",
                ssh_env,
            )

        else:

            # Local UI testing without AWS credentials
            # or Terraform/Ansible installed.

            set_state(
                status="deploying",
                message=(
                    "Demo mode: simulating Terraform..."
                ),
            )

            import time

            for message in [
                "terraform init finished",
                f"workspace '{request.env_name}' selected",
                "terraform apply running...",
            ]:

                add_log(message)
                time.sleep(0.8)

            application = "127.0.0.1:8080"

            set_state(
                application=application,
                message=(
                    "Demo Terraform finished. "
                    "Simulating Ansible..."
                ),
            )

            time.sleep(1.2)

            add_log(
                "ansible-playbook "
                "finished with exit code 0"
            )

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        set_state(
            job_id=job_id,
            status="success",
            message="Environment deployed successfully!",
            environment=request.env_name,
            backend=request.backend,
            database=request.database,
            application=application,
            error=None,
        )

    except Exception as exc:

        set_state(
            job_id=job_id,
            status="error",
            message="Deployment failed.",
            error=str(exc),
        )

    finally:

        # Stop only the SSH agent created by this deployment.
        if ssh_env is not None:
            stop_ssh_agent(ssh_env)


# ============================================================
# DESTROY
# ============================================================

def destroy_sync(
    request: DestroyRequest,
    job_id: str,
) -> None:

    ssh_env = None

    try:

        if not DEMO_MODE:

            if not TERRAFORM_DIR.exists():
                raise RuntimeError(
                    f"Terraform directory does not exist: "
                    f"{TERRAFORM_DIR}"
                )

            # Start SSH agent for the same execution environment.
            ssh_env = setup_ssh_agent()

            set_state(
                status="destroying",
                message=(
                    f"Selecting Terraform workspace "
                    f"'{request.env_name}'..."
                ),
            )

            ensure_workspace(
                request.env_name,
                ssh_env,
            )

            set_state(
                message=(
                    "Terraform is destroying "
                    "the environment..."
                )
            )

            run_command(
                [
                    "terraform",
                    "destroy",
                    "-auto-approve",
                    f"-var=backend={request.backend}",
                    f"-var=database={request.database}",
                    f"-var=env_name={request.env_name}",
                ],
                TERRAFORM_DIR,
                "terraform destroy",
                ssh_env,
            )

        else:

            import time

            set_state(
                status="destroying",
                message=(
                    "Demo mode: simulating "
                    "Terraform destroy..."
                ),
            )

            add_log(
                "terraform destroy running..."
            )

            time.sleep(1.5)

            add_log(
                "terraform destroy "
                "finished with exit code 0"
            )

        set_state(
            job_id=job_id,
            status="destroyed",
            message="Environment destroyed.",
            application=None,
            error=None,
        )

    except Exception as exc:

        set_state(
            status="error",
            message="Destroy failed.",
            error=str(exc),
        )

    finally:

        if ssh_env is not None:
            stop_ssh_agent(ssh_env)


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ============================================================
# STATUS
# ============================================================

@app.get("/api/status")
def get_status() -> dict[str, Any]:
    return snapshot()


# ============================================================
# DEPLOY
# ============================================================

@app.post("/api/deploy", status_code=202)
async def deploy(
    request: DeployRequest,
) -> dict[str, Any]:

    current = snapshot()

    if current["status"] in {
        "deploying",
        "destroying",
    }:

        raise HTTPException(
            status_code=409,
            detail="Another operation is already running.",
        )

    job_id = str(uuid.uuid4())

    set_state(
        job_id=job_id,
        status="deploying",
        message="Deployment started...",
        environment=request.env_name,
        backend=request.backend,
        database=request.database,
        application=None,
        logs=[],
        error=None,
    )

    asyncio.create_task(
        asyncio.to_thread(
            deploy_sync,
            request,
            job_id,
        )
    )

    return {
        "job_id": job_id,
        "status": "deploying",
    }


# ============================================================
# DESTROY
# ============================================================

@app.post("/api/destroy", status_code=202)
async def destroy(
    request: DestroyRequest,
) -> dict[str, Any]:

    current = snapshot()

    if current["status"] in {
        "deploying",
        "destroying",
    }:

        raise HTTPException(
            status_code=409,
            detail="Another operation is already running.",
        )

    if current["environment"] != request.env_name:

        raise HTTPException(
            status_code=400,
            detail=(
                "The requested environment "
                "is not the active environment."
            ),
        )

    job_id = str(uuid.uuid4())

    set_state(
        job_id=job_id,
        status="destroying",
        message="Destroy started...",
        error=None,
    )

    asyncio.create_task(
        asyncio.to_thread(
            destroy_sync,
            request,
            job_id,
        )
    )

    return {
        "job_id": job_id,
        "status": "destroying",
    }