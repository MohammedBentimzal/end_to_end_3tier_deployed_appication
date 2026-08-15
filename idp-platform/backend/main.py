"""
IDP Self-Service Orchestrator — FastAPI backend.

Wraps the existing Terraform + Ansible workflow behind a small REST API,
so a developer can request an environment through a web form instead of
running terraform/ansible commands by hand.

IMPORTANT — how "waiting for terraform apply to finish" actually works:
subprocess.run() is *blocking* by nature — it does not return until the
child process exits. There is no need for a fixed sleep/timeout to guess
when a command is "probably done"; run() already waits for the real exit
code. The only thing we need to be careful about is not blocking the HTTP
request itself while that happens (terraform apply can take minutes) —
that's why the actual provisioning work runs inside a FastAPI
BackgroundTask, and the frontend polls GET /api/status/{env_name} instead
of waiting on a single long HTTP call.
"""

import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Configuration — adjust these paths to match where your terraform/ and
# ansible/ folders actually live on this machine.
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TERRAFORM_DIR = os.environ.get(
    "IDP_TERRAFORM_DIR", os.path.join(BASE_DIR, "..", "..", "terraform")
)
ANSIBLE_DIR = os.environ.get(
    "IDP_ANSIBLE_DIR", os.path.join(BASE_DIR, "..", "..", "ansible")
)
ANSIBLE_INVENTORY = os.environ.get("IDP_ANSIBLE_INVENTORY", "inventory.aws_ec2.yaml")

# Command timeouts (seconds) — safety nets only, not the primary "wait"
# mechanism. subprocess.run() already blocks until the command finishes;
# these just prevent a truly hung command from blocking a request forever.
TERRAFORM_TIMEOUT = int(os.environ.get("IDP_TERRAFORM_TIMEOUT", "900"))   # 15 min
ANSIBLE_TIMEOUT = int(os.environ.get("IDP_ANSIBLE_TIMEOUT", "900"))       # 15 min

# ---------------------------------------------------------------------------
# In-memory store of deployments.
#
# This is intentionally simple for local/dev testing: a plain dict, guarded
# by a lock, living in the FastAPI process's memory. Restarting the server
# forgets all deployment history (the real AWS resources are of course
# unaffected — only this tracking dict is lost). For anything beyond local
# testing, replace this with a real database.
# ---------------------------------------------------------------------------

_store_lock = threading.Lock()
deployments: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update_deployment(key: str, **fields):
    with _store_lock:
        deployments.setdefault(key, {})
        deployments[key].update(fields)
        deployments[key]["updated_at"] = _now()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class Backend(str, Enum):
    django = "django"
    gin = "gin"


class Database(str, Enum):
    postgres = "postgres"
    mysql = "mysql"
    mongo = "mongo"


ENV_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,30}$")


class ProvisionRequest(BaseModel):
    backend: Backend
    database: Database
    env_name: str

    @field_validator("env_name")
    @classmethod
    def validate_env_name(cls, v: str) -> str:
        if not ENV_NAME_PATTERN.match(v):
            raise ValueError(
                "env_name must start with a lowercase letter, be 2-31 chars, "
                "and contain only lowercase letters, numbers, - or _"
            )
        # Ansible/Terraform group and workspace names are cleaner with
        # underscores (hyphens get silently rewritten by Ansible's dynamic
        # inventory), so normalise here once, in one place.
        return v.replace("-", "_")


class DestroyRequest(BaseModel):
    env_name: str


class DeploymentStatus(BaseModel):
    env_name: str
    backend: Optional[str] = None
    database: Optional[str] = None
    status: str
    url: Optional[str] = None
    error: Optional[str] = None
    logs: list[str] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------

class CommandFailed(Exception):
    def __init__(self, cmd: list[str], returncode: int, stdout: str, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(f"Command {' '.join(cmd)} exited with {returncode}")


def run_cmd(cmd: list[str], cwd: str, timeout: int, extra_env: Optional[dict] = None) -> str:
    """
    Runs a command and blocks until it finishes (this is the actual
    "wait for completion" mechanism — subprocess.run() only returns once
    the child process has exited, with the real returncode available).
    Raises CommandFailed if the command exits non-zero.
    """
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise CommandFailed(cmd, result.returncode, result.stdout, result.stderr)
    return result.stdout


def terraform_cmd(*args: str) -> list[str]:
    return ["terraform", *args]


def ansible_extra_env() -> dict:
    # Disables SSH host-key prompts, which would otherwise hang a
    # non-interactive subprocess call the first time Ansible connects to
    # a freshly created instance (new instances always have a new,
    # never-before-seen host key).
    return {"ANSIBLE_HOST_KEY_CHECKING": "False"}


# ---------------------------------------------------------------------------
# Provisioning / destruction workflows (run inside background tasks)
# ---------------------------------------------------------------------------

def provision_environment(backend: str, database: str, env_name: str):
    logs: list[str] = []

    def log(line: str):
        logs.append(line)
        _update_deployment(env_name, logs=list(logs))

    try:
        _update_deployment(
            env_name,
            env_name=env_name,
            backend=backend,
            database=database,
            status="provisioning",
            error=None,
            url=None,
        )

        log("terraform init")
        run_cmd(terraform_cmd("init", "-input=false"), TERRAFORM_DIR, TERRAFORM_TIMEOUT)

        log(f"terraform workspace new/select {env_name}")
        # "new" fails harmlessly if the workspace already exists — that's
        # fine, we just want to be sure it's selected either way.
        subprocess.run(
            terraform_cmd("workspace", "new", env_name),
            cwd=TERRAFORM_DIR, capture_output=True, text=True,
        )
        run_cmd(terraform_cmd("workspace", "select", env_name), TERRAFORM_DIR, TERRAFORM_TIMEOUT)

        log("terraform apply")
        run_cmd(
            terraform_cmd(
                "apply", "-auto-approve", "-input=false",
                f"-var=backend={backend}",
                f"-var=database={database}",
                f"-var=env_name={env_name}",
            ),
            TERRAFORM_DIR, TERRAFORM_TIMEOUT,
        )

        log("terraform output nginx_public_ip")
        ip_output = run_cmd(
            terraform_cmd("output", "-raw", "nginx_public_ip"),
            TERRAFORM_DIR, 60,
        ).strip()

        _update_deployment(env_name, url=f"http://{ip_output}")

        log("ansible-playbook site.yaml")
        run_cmd(
            [
                "ansible-playbook",
                "-i", ANSIBLE_INVENTORY,
                "site.yaml",
                "-e", f"backend_type={backend} db_engine={database} env_name={env_name}",
                "--limit", env_name,
            ],
            ANSIBLE_DIR, ANSIBLE_TIMEOUT,
            extra_env=ansible_extra_env(),
        )

        log("done")
        _update_deployment(env_name, status="ready")

    except CommandFailed as e:
        log(f"FAILED: {' '.join(e.cmd)}")
        _update_deployment(
            env_name,
            status="failed",
            error=(e.stderr or e.stdout or str(e))[-4000:],
        )
    except subprocess.TimeoutExpired as e:
        log(f"TIMEOUT: {e}")
        _update_deployment(env_name, status="failed", error=f"Command timed out: {e}")
    except Exception as e:  # noqa: BLE001 — surface any unexpected error to the UI
        log(f"ERROR: {e}")
        _update_deployment(env_name, status="failed", error=str(e))


def destroy_environment(env_name: str):
    logs = deployments.get(env_name, {}).get("logs", [])

    def log(line: str):
        logs.append(line)
        _update_deployment(env_name, logs=list(logs))

    try:
        backend = deployments.get(env_name, {}).get("backend")
        database = deployments.get(env_name, {}).get("database")

        _update_deployment(env_name, status="destroying", error=None)

        log(f"terraform workspace select {env_name}")
        run_cmd(terraform_cmd("workspace", "select", env_name), TERRAFORM_DIR, TERRAFORM_TIMEOUT)

        log("terraform destroy")
        run_cmd(
            terraform_cmd(
                "destroy", "-auto-approve", "-input=false",
                f"-var=backend={backend}",
                f"-var=database={database}",
                f"-var=env_name={env_name}",
            ),
            TERRAFORM_DIR, TERRAFORM_TIMEOUT,
        )

        log("done")
        _update_deployment(env_name, status="destroyed", url=None)

    except CommandFailed as e:
        log(f"FAILED: {' '.join(e.cmd)}")
        _update_deployment(
            env_name,
            status="destroy_failed",
            error=(e.stderr or e.stdout or str(e))[-4000:],
        )
    except Exception as e:  # noqa: BLE001
        log(f"ERROR: {e}")
        _update_deployment(env_name, status="destroy_failed", error=str(e))


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="IDP Self-Service Orchestrator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # vite dev server
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/provision", response_model=DeploymentStatus)
def provision(req: ProvisionRequest, background_tasks: BackgroundTasks):
    existing = deployments.get(req.env_name)
    if existing and existing.get("status") in ("provisioning", "destroying"):
        raise HTTPException(
            status_code=409,
            detail=f"Environment '{req.env_name}' already has a request in progress.",
        )

    _update_deployment(
        req.env_name,
        env_name=req.env_name,
        backend=req.backend.value,
        database=req.database.value,
        status="queued",
        error=None,
        url=None,
        logs=[],
        created_at=_now(),
    )

    background_tasks.add_task(
        provision_environment, req.backend.value, req.database.value, req.env_name
    )

    return deployments[req.env_name]


@app.post("/api/destroy", response_model=DeploymentStatus)
def destroy(req: DestroyRequest, background_tasks: BackgroundTasks):
    existing = deployments.get(req.env_name)
    if not existing:
        raise HTTPException(status_code=404, detail="Unknown environment.")
    if existing.get("status") not in ("ready", "failed"):
        raise HTTPException(
            status_code=409,
            detail=f"Environment '{req.env_name}' is not in a destroyable state "
                   f"(current status: {existing.get('status')}).",
        )

    background_tasks.add_task(destroy_environment, req.env_name)
    return deployments[req.env_name]


@app.get("/api/status/{env_name}", response_model=DeploymentStatus)
def get_status(env_name: str):
    existing = deployments.get(env_name)
    if not existing:
        raise HTTPException(status_code=404, detail="Unknown environment.")
    return existing


@app.get("/api/deployments", response_model=list[DeploymentStatus])
def list_deployments():
    return list(deployments.values())


@app.get("/api/health")
def health():
    return {"status": "ok"}
