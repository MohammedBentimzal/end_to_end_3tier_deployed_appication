# IDP Self-Service Platform (Week 5)

A small web application that wraps the project's existing Terraform +
Ansible workflow behind a form: a developer picks a backend, a database,
and an environment name, clicks **Apply**, and gets back a public URL once
the environment is provisioned and configured — without ever touching
Terraform or Ansible themselves.

```
Browser (React)  →  FastAPI backend  →  subprocess: terraform / ansible-playbook  →  AWS
```

## 1. How "waiting for terraform apply to finish" actually works

This was the open question going into this build. The answer:
**`subprocess.run()` is blocking by nature — it does not return until the
child process has actually exited**, with the real exit code available on
`result.returncode`. There is no need for a fixed timer (`sleep(300)`) to
*guess* when a command is done; `run()` already tells you exactly when it
finished and whether it succeeded.

The only real problem this creates is that `terraform apply` /
`ansible-playbook` can take several minutes — long enough that blocking an
HTTP request on it would hang the browser and risk timeouts. That's solved
by running the actual provisioning work inside a **FastAPI
`BackgroundTask`**: the `POST /api/provision` request returns immediately
(status `"queued"`), and the real work — the blocking `subprocess.run()`
calls — happens afterward, in the background. The React frontend then
**polls** `GET /api/status/{env_name}` every 3 seconds until the status
changes to `"ready"` or `"failed"`.

A generous `timeout=` is still set on each `subprocess.run()` call (15
minutes by default) purely as a safety net against a genuinely hung
command — not as the primary completion-detection mechanism.

## 2. Project layout

```
idp-platform/
  backend/
    main.py              # FastAPI orchestrator
    requirements.txt
  frontend/
    src/
      App.jsx             # form, polling, status/destroy UI
      App.css
      main.jsx
    index.html
    package.json
    vite.config.js
  README.md               # this file
```

## 3. Backend — what it actually does

`POST /api/provision` with `{ backend, database, env_name }`:

1. Validates the request — `backend`/`database` are Pydantic enums, so
   only `django`/`gin` and `postgres`/`mysql`/`mongo` are ever accepted;
   anything else is rejected with a 422 before any command runs.
2. Immediately returns `{ status: "queued", ... }` and schedules the real
   work as a background task.
3. In the background, runs, in order, exactly the commands you'd run by
   hand:
   ```bash
   terraform init -input=false
   terraform workspace new <env_name>      # ignored if it already exists
   terraform workspace select <env_name>
   terraform apply -auto-approve \
     -var="backend=<backend>" -var="database=<database>" -var="env_name=<env_name>"
   terraform output -raw nginx_public_ip
   ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook \
     -i inventory.aws_ec2.yaml site.yaml \
     -e "backend_type=<backend> db_engine=<database> env_name=<env_name>" \
     --limit "<env_name>"
   ```
4. Updates an in-memory status record after each step (`queued` →
   `provisioning` → `ready`, or `failed` with the captured error output).

**Why `ANSIBLE_HOST_KEY_CHECKING=False`**: a freshly created EC2 instance
has a host SSH key Ansible has never seen before. Interactively, Ansible
would prompt *"are you sure you want to continue connecting?"* — but a
non-interactive `subprocess` call has no terminal to answer that prompt,
so it would hang forever waiting for input. Disabling host-key checking
(acceptable for short-lived, disposable dev/demo environments like these)
lets the connection proceed automatically.

`POST /api/destroy` with `{ env_name }` follows the same pattern:
selects the workspace, runs `terraform destroy -auto-approve` with the
same variables, and updates the status to `destroyed` (or
`destroy_failed`, with the error captured).

`GET /api/status/{env_name}` returns the current state — this is what the
frontend polls.

**Storage note**: deployment state lives in a plain in-memory Python dict
for this local/testing build. Restarting the FastAPI process forgets the
tracking history (the real AWS resources are unaffected — only the UI's
memory of them is lost). For anything beyond local testing, replace
`deployments = {}` with a real database.

## 4. Frontend — what it actually does

A single-page React app (Vite):
- Two `<select>` dropdowns (backend, database) and a text input
  (environment name).
- **Apply** calls `POST /api/provision`, then starts polling
  `GET /api/status/{env_name}` every 3 seconds.
- While `status` is `queued`/`provisioning`/`destroying`, shows a spinner
  and disables the form.
- Once `status` becomes `ready`, shows the public URL (as a clickable
  link), the status badge, the workspace/environment name, and the chosen
  stack — plus a **Destroy Environment** button.
- If `status` becomes `failed`, shows the captured error message instead.
- A collapsible "Show logs" section displays the step-by-step log lines
  captured from the backend, useful for seeing exactly which command is
  currently running or which one failed.

## 5. Running it locally

### Prerequisites
- Python 3.10+
- Node.js 18+
- Your existing `terraform/` and `ansible/` project folders, already
  working from Weeks 2–4 (AWS credentials configured, SSH key available,
  S3 backend set up, `inventory.aws_ec2.yaml` present).

### Step 1 — point the backend at your actual terraform/ansible folders

By default, `backend/main.py` expects `terraform/` and `ansible/` two
levels above `backend/` (i.e. as siblings of this `idp-platform/` folder).
If your project is laid out differently, set these environment variables
before starting the backend:

```bash
export IDP_TERRAFORM_DIR=/absolute/path/to/idp-aws/terraform
export IDP_ANSIBLE_DIR=/absolute/path/to/idp-aws/ansible
```

### Step 2 — start the backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Confirm it's up: `curl http://localhost:8000/api/health` → `{"status":"ok"}`

### Step 3 — start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (typically `http://localhost:5173`).

### Step 4 — use it

1. Pick a backend and database, type an environment name (e.g. `alice_dev`).
2. Click **Apply (Provision & Deploy)**.
3. Watch the status update every few seconds — this can take several
   minutes, matching how long `terraform apply` + `ansible-playbook`
   actually take.
4. Once ready, click the public URL to open the deployed application.
5. Click **Destroy Environment** when done to clean everything up.

## 6. Known limitations (intentional, for this stage of the project)

- **Single machine, not a real server**: the FastAPI backend runs the
  same `terraform`/`ansible-playbook` commands you'd type by hand, on
  this machine, using its local AWS credentials and SSH key. A production
  version would run this orchestrator on a dedicated server, not a
  developer's laptop.
- **No authentication**: anyone who can reach the API can provision or
  destroy environments. Fine for local testing; a real deployment would
  need to add auth before exposing this beyond localhost.
- **One request at a time, effectively**: background tasks in this build
  run sequentially against the same local Terraform working directory.
  Since each environment already gets its own isolated Terraform
  workspace, concurrent provisioning is *safe* in principle, but this
  simple implementation processes them one after another rather than
  truly in parallel. A production version would run each request in an
  isolated working directory/container to allow real concurrency.
- **In-memory deployment tracking**: see the storage note above — replace
  with a real database for anything beyond local testing.
