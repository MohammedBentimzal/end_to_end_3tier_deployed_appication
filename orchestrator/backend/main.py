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
            raise ValueError(f"backend must be one of: {', '.join(sorted(ALLOWED_BACKENDS))}")
        return value

    @field_validator("database")
    @classmethod
    def validate_database(cls, value: str) -> str:
        if value not in ALLOWED_DATABASES:
            raise ValueError(f"database must be one of: {', '.join(sorted(ALLOWED_DATABASES))}")
        return value

    @field_validator("env_name")
    @classmethod
    def validate_env_name(cls, value: str) -> str:
        if not ENV_NAME_RE.fullmatch(value):
            raise ValueError("Use 1-40 characters: letters, numbers, '-' or '_'.")
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


def run_command(args: list[str], cwd: Path, label: str) -> subprocess.CompletedProcess[str]:
    """Run one CLI command and wait until it finishes.

    Because deployment runs in a background thread, this blocking subprocess.run()
    does not block FastAPI's main event loop.
    """
    command = " ".join(args)
    add_log(f"$ {command}")
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )
    if result.stdout:
        for line in result.stdout.splitlines():
            add_log(line)
    if result.stderr:
        for line in result.stderr.splitlines():
            add_log(f"[stderr] {line}")
    add_log(f"{label} finished with exit code {result.returncode}")
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")
    return result


def ensure_workspace(env_name: str) -> None:
    """Select an existing workspace, or create it when it does not exist.

    `workspace new` followed by `workspace select` is redundant. The select-or-create
    flow also makes a second deployment to the same environment work.
    """
    selected = subprocess.run(
        ["terraform", "workspace", "select", env_name],
        cwd=str(TERRAFORM_DIR),
        text=True,
        capture_output=True,
        check=False,
    )
    if selected.returncode == 0:
        add_log(f"Terraform workspace '{env_name}' selected.")
        return

    run_command(["terraform", "workspace", "new", env_name], TERRAFORM_DIR, "terraform workspace new")
    run_command(["terraform", "workspace", "select", env_name], TERRAFORM_DIR, "terraform workspace select")


def get_public_ip() -> str | None:
    result = subprocess.run(
        ["terraform", "output", "-raw", "public_ip"],
        cwd=str(TERRAFORM_DIR),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        value = result.stdout.strip()
        if value:
            return value

    # Fallback if the Terraform output is named `application` instead.
    result = subprocess.run(
        ["terraform", "output", "-raw", "application"],
        cwd=str(TERRAFORM_DIR),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def deploy_sync(request: DeployRequest, job_id: str) -> None:
    try:
        if not DEMO_MODE:
            if not TERRAFORM_DIR.exists():
                raise RuntimeError(f"Terraform directory does not exist: {TERRAFORM_DIR}")
            if not ANSIBLE_DIR.exists():
                raise RuntimeError(f"Ansible directory does not exist: {ANSIBLE_DIR}")

            set_state(status="deploying", message="Initializing Terraform...", error=None)
            run_command(["terraform", "init"], TERRAFORM_DIR, "terraform init")

            set_state(message=f"Selecting Terraform workspace '{request.env_name}'...")
            ensure_workspace(request.env_name)

            set_state(message="Terraform is provisioning the infrastructure...")
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
            )

            application = get_public_ip()
            if not application:
                raise RuntimeError(
                    "Terraform finished, but no public IP was found. Add a Terraform output named 'public_ip'."
                )

            set_state(application=application, message="Terraform finished. Running Ansible...")
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
            )
        else:
            # Local UI testing without AWS credentials or Terraform/Ansible installed.
            set_state(status="deploying", message="Demo mode: simulating Terraform...")
            import time
            for message in [
                "terraform init finished",
                f"workspace '{request.env_name}' selected",
                "terraform apply running...",
            ]:
                add_log(message)
                time.sleep(0.8)
            application = "127.0.0.1:8080"
            set_state(application=application, message="Demo Terraform finished. Simulating Ansible...")
            time.sleep(1.2)
            add_log("ansible-playbook finished with exit code 0")

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


def destroy_sync(request: DestroyRequest, job_id: str) -> None:
    try:
        if not DEMO_MODE:
            if not TERRAFORM_DIR.exists():
                raise RuntimeError(f"Terraform directory does not exist: {TERRAFORM_DIR}")

            set_state(status="destroying", message=f"Selecting Terraform workspace '{request.env_name}'...")
            ensure_workspace(request.env_name)
            set_state(message="Terraform is destroying the environment...")
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
            )
        else:
            import time
            set_state(status="destroying", message="Demo mode: simulating Terraform destroy...")
            add_log("terraform destroy running...")
            time.sleep(1.5)
            add_log("terraform destroy finished with exit code 0")

        set_state(
            job_id=job_id,
            status="destroyed",
            message="Environment destroyed.",
            application=None,
            error=None,
        )
    except Exception as exc:
        set_state(status="error", message="Destroy failed.", error=str(exc))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def get_status() -> dict[str, Any]:
    return snapshot()


@app.post("/api/deploy", status_code=202)
async def deploy(request: DeployRequest) -> dict[str, Any]:
    current = snapshot()
    if current["status"] in {"deploying", "destroying"}:
        raise HTTPException(status_code=409, detail="Another operation is already running.")

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
    asyncio.create_task(asyncio.to_thread(deploy_sync, request, job_id))
    return {"job_id": job_id, "status": "deploying"}


@app.post("/api/destroy", status_code=202)
async def destroy(request: DestroyRequest) -> dict[str, Any]:
    current = snapshot()
    if current["status"] in {"deploying", "destroying"}:
        raise HTTPException(status_code=409, detail="Another operation is already running.")
    if current["environment"] != request.env_name:
        raise HTTPException(status_code=400, detail="The requested environment is not the active environment.")

    job_id = str(uuid.uuid4())
    set_state(job_id=job_id, status="destroying", message="Destroy started...", error=None)
    asyncio.create_task(asyncio.to_thread(destroy_sync, request, job_id))
    return {"job_id": job_id, "status": "destroying"}
