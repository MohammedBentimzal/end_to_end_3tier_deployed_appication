import { useEffect, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const BACKEND_OPTIONS = [
  { value: "django", label: "Django" },
  { value: "gin", label: "Gin" },
];

const DATABASE_OPTIONS = [
  { value: "postgres", label: "PostgreSQL" },
  { value: "mysql", label: "MySQL" },
  { value: "mongo", label: "MongoDB" },
];

const ACTIVE_STATUSES = ["queued", "provisioning", "destroying"];

export default function App() {
  const [backend, setBackend] = useState("");
  const [database, setDatabase] = useState("");
  const [envName, setEnvName] = useState("");
  const [deployment, setDeployment] = useState(null);
  const [formError, setFormError] = useState("");
  const pollRef = useRef(null);

  useEffect(() => {
    return () => clearInterval(pollRef.current);
  }, []);

  function startPolling(name) {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/status/${name}`);
        if (!res.ok) return;
        const data = await res.json();
        setDeployment(data);
        if (!ACTIVE_STATUSES.includes(data.status)) {
          clearInterval(pollRef.current);
        }
      } catch {
        // network hiccup during polling — next tick will retry
      }
    }, 3000);
  }

  async function handleApply(e) {
    e.preventDefault();
    setFormError("");

    if (!backend || !database || !envName.trim()) {
      setFormError("Please choose a backend, a database, and an environment name.");
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/provision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backend, database, env_name: envName.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setFormError(data.detail || "Could not start provisioning.");
        return;
      }
      setDeployment(data);
      startPolling(data.env_name);
    } catch (err) {
      setFormError("Could not reach the orchestrator API. Is the backend running?");
    }
  }

  async function handleDestroy() {
    if (!deployment) return;
    try {
      const res = await fetch(`${API_BASE}/api/destroy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ env_name: deployment.env_name }),
      });
      const data = await res.json();
      if (!res.ok) {
        setFormError(data.detail || "Could not start destroy.");
        return;
      }
      setDeployment(data);
      startPolling(data.env_name);
    } catch {
      setFormError("Could not reach the orchestrator API. Is the backend running?");
    }
  }

  const isBusy = deployment && ACTIVE_STATUSES.includes(deployment.status);
  const isReady = deployment && deployment.status === "ready";
  const isFailed =
    deployment && (deployment.status === "failed" || deployment.status === "destroy_failed");
  const isDestroyed = deployment && deployment.status === "destroyed";

  return (
    <div className="page">
      <header className="hero">
        <div className="hero-icon">☁</div>
        <h1>Self-Service Platform</h1>
        <p className="tagline">Build. Deploy. Scale.</p>
        <p className="subtitle">
          This platform provisions a complete environment on the cloud using
          Terraform and configures it with Ansible.
        </p>
      </header>

      <section className="card">
        <div className="card-header">
          <span className="card-icon">🚀</span>
          <div>
            <h2>Deploy a New Environment</h2>
            <p className="muted">
              Choose your application stack and environment name. The platform
              will provision the infrastructure (Terraform) and configure it
              (Ansible).
            </p>
          </div>
        </div>

        <form onSubmit={handleApply}>
          <div className="field-row">
            <div className="field">
              <label>
                <span className="field-icon">{"</>"}</span> Backend Framework
              </label>
              <select
                value={backend}
                onChange={(e) => setBackend(e.target.value)}
                disabled={isBusy}
              >
                <option value="">Select backend</option>
                {BACKEND_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <p className="hint">
                Only validated choices: <b>django</b>, <b>gin</b>
              </p>
            </div>

            <div className="field">
              <label>
                <span className="field-icon">🗄</span> Database Engine
              </label>
              <select
                value={database}
                onChange={(e) => setDatabase(e.target.value)}
                disabled={isBusy}
              >
                <option value="">Select database</option>
                {DATABASE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <p className="hint">
                Only validated choices: <b>postgres</b>, <b>mysql</b>, <b>mongo</b>
              </p>
            </div>
          </div>

          <div className="field">
            <label>
              <span className="field-icon">🏷</span> Environment Name
            </label>
            <input
              type="text"
              placeholder="e.g. dev, staging, prod"
              value={envName}
              onChange={(e) => setEnvName(e.target.value)}
              disabled={isBusy}
            />
            <p className="hint">Used to create a unique workspace and resources.</p>
          </div>

          {formError && <p className="error-text">{formError}</p>}

          <button type="submit" className="apply-btn" disabled={isBusy}>
            {isBusy ? "Working…" : "▶ Apply (Provision & Deploy)"}
          </button>
          <p className="apply-note">
            This will run Terraform first, then Ansible, in sequence.
          </p>
        </form>
      </section>

      {deployment && (
        <section className="card">
          {isBusy && (
            <div className="status-block">
              <span className="spinner" />
              <div>
                <h3>
                  {deployment.status === "destroying"
                    ? "Destroying environment…"
                    : "Deploying environment…"}
                </h3>
                <p className="muted">This can take a few minutes.</p>
              </div>
            </div>
          )}

          {isReady && (
            <div className="status-block success">
              <span className="status-icon">✓</span>
              <div>
                <h3>Environment Deployed Successfully!</h3>
                <p className="muted">Your environment is ready.</p>
              </div>
            </div>
          )}

          {isFailed && (
            <div className="status-block failure">
              <span className="status-icon">✕</span>
              <div>
                <h3>
                  {deployment.status === "destroy_failed"
                    ? "Destroy failed"
                    : "Deployment failed"}
                </h3>
                <p className="muted">{deployment.error}</p>
              </div>
            </div>
          )}

          {isDestroyed && (
            <div className="status-block">
              <h3>Environment destroyed</h3>
              <p className="muted">All resources for this environment were removed.</p>
            </div>
          )}

          {(isReady || isFailed) && deployment.url && (
            <div className="details-grid">
              <div>
                <p className="detail-label">🌐 Public Access URL</p>
                <a href={deployment.url} target="_blank" rel="noreferrer" className="url-link">
                  {deployment.url.replace("http://", "")}
                </a>
              </div>
              <div>
                <p className="detail-label">Status</p>
                <span className="badge">{deployment.status.toUpperCase()}</span>
              </div>
              <div>
                <p className="detail-label">Workspace</p>
                <span className="workspace-name">{deployment.env_name}</span>
              </div>
              <div>
                <p className="detail-label">Stack</p>
                <span className="workspace-name">
                  {deployment.backend} + {deployment.database}
                </span>
              </div>
            </div>
          )}

          {(isReady || isFailed) && (
            <>
              <hr className="divider" />
              <button className="destroy-btn" onClick={handleDestroy} disabled={isBusy}>
                🗑 Destroy Environment
              </button>
              <p className="apply-note">
                This will destroy all resources and remove the workspace.
              </p>
            </>
          )}

          {deployment.logs && deployment.logs.length > 0 && (
            <details className="logs">
              <summary>Show logs</summary>
              <pre>{deployment.logs.join("\n")}</pre>
            </details>
          )}
        </section>
      )}

      <footer className="notice">
        <p>
          <b>Important:</b> only the following options are allowed — Backend:
          django, gin · Database: postgres, mysql, mongo. All environments are
          isolated and automatically configured.
        </p>
      </footer>
    </div>
  );
}
