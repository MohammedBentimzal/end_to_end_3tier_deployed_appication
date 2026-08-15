# Self-Service Platform — React + FastAPI + Terraform + Ansible

A local self-service Infrastructure-as-Code web application based on the supplied UI reference.

The user chooses:

- Backend: `django` or `gin`
- Database: `postgres`, `mysql`, or `mongo`
- Environment name: for example `dev`, `staging`, `prod`

Then the workflow is:

```text
React in browser
    |
    | POST /api/deploy
    v
FastAPI
    |
    | background thread + subprocess.run()
    v
terraform init
    |
terraform workspace select <env>  (or workspace new if it does not exist)
    |
terraform apply -var=backend=... -var=database=... -var=env_name=...
    |
    v
Terraform output -raw public_ip
    |
ansible-playbook ... --limit <env>
    |
    v
FastAPI status = success
    |
    v
React displays public IP + environment + backend + database + Destroy button
```

## Why the implementation does not use a fixed 5-minute timer

`terraform apply` and `ansible-playbook` can finish in 20 seconds or 20 minutes. A fixed sleep such as `sleep(300)` is therefore unreliable.

The backend uses `subprocess.run()`, which **waits until the command actually exits** and gives Python the exit code/stdout/stderr. The deployment itself runs in a background thread so the FastAPI event loop remains available.

The React frontend polls `GET /api/status` every ~1.2 seconds. When the backend changes the state to `success`, JavaScript displays the successful deployment card.

## Important workspace detail

The requested sequence was:

```text
terraform workspace new <env>
terraform workspace select <env>
```

`workspace new` already creates **and selects** the workspace, and it fails if the workspace already exists. Therefore this project uses:

```text
terraform workspace select <env>
```

and, only if that fails:

```text
terraform workspace new <env>
terraform workspace select <env>
```

That makes redeploying an existing environment possible.

## Project structure

```text
self-service-platform/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       └── styles.css
├── infra/
│   ├── terraform/
│   │   └── README.md
│   └── ansible/
│       └── README.md
├── design-reference.png
├── .gitignore
└── README.md
```

## 1. Test the UI locally without AWS

This is the easiest first test.

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
DEMO_MODE=true uvicorn main:app --reload --port 8000
```

FastAPI will be available at:

```text
http://localhost:8000
```

### Frontend 

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

In demo mode, no Terraform, AWS, or Ansible command is executed. The backend simulates the process and returns `127.0.0.1:8080` as the application address so you can test the full UI workflow.

## 2. Connect your real Terraform and Ansible project

When you are ready to execute your real infrastructure code, stop the backend and start it with `DEMO_MODE=false` (the default):

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

By default, the backend expects:

```text
self-service-platform/infra/terraform/
self-service-platform/infra/ansible/
```

If your existing Terraform and Ansible directories are elsewhere, set:

```bash
export TERRAFORM_DIR=/home/you/path/to/terraform
export ANSIBLE_DIR=/home/you/path/to/ansible
export ANSIBLE_INVENTORY=inventory.aws_ec2.yaml
export ANSIBLE_PLAYBOOK=site.yaml
```

Then start Uvicorn.

## 3. Terraform requirements

Your Terraform configuration should define variables corresponding to:

```text
backend
database
env_name
```

For example:

```hcl
variable "backend" {
  type = string
}

variable "database" {
  type = string
}

variable "env_name" {
  type = string
}
```

The backend executes:

```bash
terraform apply -auto-approve \
  -var=backend=django \
  -var=database=postgres \
  -var=env_name=dev
```

### Public IP output

The FastAPI application stores the deployed address in the Python variable named `application`.

For this to work with real Terraform, expose the public IP as a Terraform output:

```hcl
output "public_ip" {
  value = aws_instance.your_instance.public_ip
}
```

After `terraform apply`, FastAPI runs:

```bash
terraform output -raw public_ip
```

and stores the result in `application`.

The code also tries an output named `application` as a fallback.

## 4. Ansible command used by the backend

The backend runs the equivalent of:

```bash
ansible-playbook \
  -i inventory.aws_ec2.yaml \
  site.yaml \
  -e backend_type=django \
  -e db_engine=postgres \
  -e env_name=dev \
  --limit dev
```

The values come from the React form and are validated by FastAPI before being passed as separate subprocess arguments.

## 5. Destroy workflow

Clicking **Destroy Environment** sends:

```text
POST /api/destroy
```

FastAPI selects the environment workspace and runs:

```bash
terraform destroy -auto-approve \
  -var=backend=django \
  -var=database=postgres \
  -var=env_name=dev
```

`-auto-approve` is intentional: a web API cannot stop and wait for an interactive terminal confirmation.

## 6. REST API

### Health

```http
GET /api/health
```

### Get current operation status

```http
GET /api/status
```

Example response:

```json
{
  "status": "success",
  "message": "Environment deployed successfully!",
  "environment": "dev",
  "backend": "django",
  "database": "postgres",
  "application": "3.21.45.67",
  "error": null
}
```

### Start deployment

```http
POST /api/deploy
Content-Type: application/json

{
  "backend": "django",
  "database": "postgres",
  "env_name": "dev"
}
```

It immediately returns a job ID while the background deployment continues.

### Start destroy

```http
POST /api/destroy
Content-Type: application/json

{
  "backend": "django",
  "database": "postgres",
  "env_name": "dev"
}
```

## 7. Security notes before exposing this beyond localhost

This is a learning/local prototype, not a production-ready remote Terraform runner.

Before exposing it to other developers, add at least:

- authentication and authorization;
- per-user/per-environment ownership;
- a persistent job database instead of in-memory state;
- a real job queue/worker for long Terraform runs;
- secrets management;
- Terraform state locking and remote state;
- command timeouts and cancellation strategy;
- audit logs;
- concurrency controls so two operations cannot modify the same workspace;
- HTTPS and restricted network access;
- stronger validation of all infrastructure inputs.

Do **not** create an endpoint that accepts arbitrary shell commands from the browser. The API should expose controlled operations such as `/api/deploy` and `/api/destroy`.
