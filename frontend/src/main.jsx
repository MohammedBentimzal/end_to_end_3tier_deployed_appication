import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const backends = ['django', 'gin'];
const databases = ['postgres', 'mysql', 'mongo'];

function Icon({ children, className = '' }) {
  return <span className={`icon ${className}`} aria-hidden="true">{children}</span>;
}

function App() {
  const [backend, setBackend] = useState('');
  const [database, setDatabase] = useState('');
  const [envName, setEnvName] = useState('');
  const [status, setStatus] = useState('idle');
  const [message, setMessage] = useState('Choose your application stack and environment name.');
  const [application, setApplication] = useState(null);
  const [activeEnv, setActiveEnv] = useState(null);
  const [activeBackend, setActiveBackend] = useState(null);
  const [activeDatabase, setActiveDatabase] = useState(null);
  const [error, setError] = useState(null);
  const [logs, setLogs] = useState([]);

  const busy = status === 'deploying' || status === 'destroying';

  const syncStatus = async () => {
    try {
      const response = await fetch(`${API}/api/status`);
      const data = await response.json();
      setStatus(data.status);
      setMessage(data.message);
      setApplication(data.application);
      setActiveEnv(data.environment);
      setActiveBackend(data.backend);
      setActiveDatabase(data.database);
      setError(data.error);
      setLogs(data.logs || []);
    } catch {
      setStatus('offline');
      setMessage('FastAPI is not reachable. Start the backend on port 8000.');
    }
  };

  useEffect(() => {
    syncStatus();
    const timer = setInterval(syncStatus, 1200);
    return () => clearInterval(timer);
  }, []);

  const deploy = async () => {
    setError(null);
    if (!backend || !database || !envName.trim()) {
      setError('Please select a backend, select a database, and enter an environment name.');
      return;
    }
    try {
      const response = await fetch(`${API}/api/deploy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backend, database, env_name: envName.trim() })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not start deployment.');
      setStatus('deploying');
      setMessage('Deployment started...');
    } catch (err) {
      setError(err.message);
    }
  };

  const destroy = async () => {
    if (!window.confirm(`Destroy environment '${activeEnv}'? This will remove its infrastructure.`)) return;
    setError(null);
    try {
      const response = await fetch(`${API}/api/destroy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backend: activeBackend, database: activeDatabase, env_name: activeEnv })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not start destroy.');
      setStatus('destroying');
      setMessage('Destroy started...');
    } catch (err) {
      setError(err.message);
    }
  };

  const isSuccess = status === 'success';
  const isDestroyed = status === 'destroyed';

  return (
    <div className="page-shell">
      <Background />
      <main className="content">
        <header className="hero">
          <div className="hero-top">
            <div className="cloud-logo"><span>⌬</span></div>
            <div className="iac-badge"><Icon>♧</Icon> Infrastructure as Code</div>
          </div>
          <div className="brand">aws</div>
          <h1>Self-Service Platform</h1>
          <div className="tagline"><span>Build.</span> <b>Deploy.</b> <i>Scale.</i></div>
          <p>This platform provisions a complete environment on the cloud<br />using Terraform and configures it with Ansible.</p>
        </header>

        <section className="panel deploy-panel">
          <div className="section-heading">
            <div className="rocket">◈</div>
            <div>
              <h2>Deploy a New Environment</h2>
              <p>Choose your application stack and environment name.</p>
              <p>The platform will provision the infrastructure (Terraform) and configure it (Ansible).</p>
            </div>
          </div>

          <div className="form-grid">
            <Field label="Backend Framework" icon="〈/〉">
              <select value={backend} onChange={(e) => setBackend(e.target.value)} disabled={busy || isSuccess}>
                <option value="">Select backend</option>
                {backends.map(item => <option key={item} value={item}>{item}</option>)}
              </select>
              <small>Only validated choices: <b>django, gin</b></small>
            </Field>

            <Field label="Database Engine" icon="◉">
              <select value={database} onChange={(e) => setDatabase(e.target.value)} disabled={busy || isSuccess}>
                <option value="">Select database</option>
                {databases.map(item => <option key={item} value={item}>{item}</option>)}
              </select>
              <small>Only validated choices: <b>postgres, mysql, mongo</b></small>
            </Field>
          </div>

          <Field label="Environment Name" icon="◆" full>
            <input
              value={envName}
              onChange={(e) => setEnvName(e.target.value)}
              disabled={busy || isSuccess}
              placeholder="e.g. dev, staging, prod"
              maxLength={40}
            />
            <small>Used to create a unique workspace and resources.</small>
          </Field>

          <button className="apply-button" onClick={deploy} disabled={busy || isSuccess}>
            {status === 'deploying' ? <><span className="spinner" /> Deploying...</> : <><span className="play">▶</span> Apply (Provision &amp; Deploy)</>}
          </button>
          <div className="sequence-note"><span>◆</span> This will run Terraform first, then Ansible in <strong>sequence</strong>.</div>

          {(status === 'deploying' || status === 'destroying') && (
            <div className="progress-box">
              <div className="progress-title"><span className="spinner" /> {message}</div>
              <div className="progress-track"><div className="progress-bar" /></div>
              <div className="progress-sub">The browser polls FastAPI for completion. No fixed 5-minute timer is used.</div>
            </div>
          )}
          {error && <div className="error-box">⚠ {error}</div>}
        </section>

        {isSuccess && (
          <section className="panel success-panel">
            <div className="success-heading"><span className="check">✓</span><div><h2>Environment Deployed Successfully!</h2><p>Your environment is ready.</p></div></div>
            <div className="result-card">
              <div className="result-main">
                <div className="result-label"><span>◎</span> Public Access URL</div>
                <a className="public-ip" href={normalizeUrl(application)} target="_blank" rel="noreferrer">{application}</a>
              </div>
              <button className="copy-button" onClick={() => navigator.clipboard?.writeText(normalizeUrl(application))} title="Copy URL">▣</button>
              <div className="result-item"><span>Status</span><strong className="running">RUNNING</strong></div>
              <div className="result-item"><span>Workspace</span><strong className="workspace">{activeEnv}</strong></div>
            </div>
            <p className="access-note">You can access your application using the public IP above.</p>
            <button className="destroy-button" onClick={destroy} disabled={busy}><span>♜</span> Destroy Environment</button>
            <div className="destroy-note">This will destroy all resources and remove the workspace.</div>
          </section>
        )}

        {isDestroyed && (
          <section className="panel destroyed-panel"><span className="check">✓</span><div><h2>Environment Destroyed</h2><p>The Terraform destroy command completed successfully. You can deploy another environment.</p></div></section>
        )}

        <section className="panel important-panel">
          <div className="info-icon">i</div>
          <div><h3>Important</h3><p>Only the following options are allowed:</p><ul><li>Backend: <b>django, gin</b></li><li>Database: <b>postgres, mysql, mongo</b></li></ul></div>
          <div className="security-copy">All environments are isolated, secure,<br />and automatically configured.</div>
          <div className="shield">♢</div>
        </section>

        {logs.length > 0 && (
          <details className="logs"><summary>Deployment logs</summary><pre>{logs.join('\n')}</pre></details>
        )}
      </main>
    </div>
  );
}

function normalizeUrl(value) {
  if (!value) return '#';
  return /^https?:\/\//i.test(value) ? value : `http://${value}`;
}

function Field({ label, icon, children, full }) {
  return <div className={`field ${full ? 'full' : ''}`}><label><span>{icon}</span>{label}</label>{children}</div>;
}

function Background() {
  return <div className="background" aria-hidden="true"><div className="glow glow-one" /><div className="glow glow-two" /><div className="circuit c1" /><div className="circuit c2" /><div className="server server-left"><div /><div /><div /></div><div className="server server-right"><div /><div /><div /><div /></div><div className="cube-stack"><i /><i /><i /><i /></div><div className="side-cloud">☁</div><div className="kube">⬡</div></div>;
}

createRoot(document.getElementById('root')).render(<App />);
