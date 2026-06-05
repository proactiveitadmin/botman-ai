import { Buffer } from 'buffer'
import process from 'process'

window.Buffer = Buffer
window.process = process
import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { createCampaign, getMonthlyMetrics } from './api.js';
import { completeNewPassword, getSession, login, logout, TENANT_ID } from './auth.js';
import './styles.css';

const METRIC_LABELS = {
  TenantInboundAccepted: 'Inbound accepted',
  TenantInboundBlocked: 'Inbound blocked',
  TenantRoutedInbound: 'Routed inbound',
  TenantRoutedOk: 'Routed OK',
  TenantRoutedError: 'Routed errors',
  TenantOutboundQueued: 'Outbound queued',
  TenantOutboundSent: 'Outbound sent',
  TenantCampaignSendOk: 'Campaign sent',
};

function currentMonth() {
  return new Date().toISOString().slice(0, 7);
}

function LoginScreen({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [needsNewPassword, setNeedsNewPassword] = useState(false);
  const [error, setError] = useState('');

  async function submit(e) {
    e.preventDefault();
    setError('');
    try {
      if (needsNewPassword) {
        onLogin(await completeNewPassword({ email, newPassword }));
        return;
      }
      onLogin(await login({ email, password }));
    } catch (err) {
      if (err.code === 'NEW_PASSWORD_REQUIRED' || err.message === 'NEW_PASSWORD_REQUIRED') {
        setNeedsNewPassword(true);
        setError('Set a new permanent password to finish the first login.');
        return;
      }
      setError(err.message);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="flex justify-center items-center">
		  <img
			src="/logo.png"
			alt=".Dialo"
			className="login-logo"
		  />
		</div>
        <h1>Tenant panel</h1>
        <p className="muted">Sign in with Cognito to manage campaigns and monthly statistics.</p>
        <form className="stack" onSubmit={submit}>
          <label>
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="email" placeholder="name@example.com" disabled={needsNewPassword} />
          </label>
          {!needsNewPassword && (
            <label>
              Password
              <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" placeholder="••••••••" />
            </label>
          )}
          {needsNewPassword && (
            <label>
              New password
              <input value={newPassword} onChange={(e) => setNewPassword(e.target.value)} type="password" autoComplete="new-password" placeholder="Minimum 10 characters" />
            </label>
          )}
          {error && <div className="alert error">{error}</div>}
          <button className="primary" type="submit">{needsNewPassword ? 'Set password and log in' : 'Log in'}</button>
        </form>
        <p className="hint">Authentication is handled by AWS Cognito. API calls use a Cognito JWT Bearer token.</p>
      </section>
    </main>
  );
}

function CampaignForm() {
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [body, setBody] = useState('');
  const [phonesText, setPhonesText] = useState('');
  const [scheduledAt, setScheduledAt] = useState(() => {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    return now.toISOString().slice(0, 16);
  });
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);

  const phones = useMemo(() => phonesText.split(/[\n,;]+/).map((x) => x.trim()).filter(Boolean), [phonesText]);

  async function submit(e) {
    e.preventDefault();
    setStatus(null);
    setLoading(true);
    try {
      const result = await createCampaign({ body: body.trim(), phones, scheduledAt });
      setStatus({ type: 'success', text: `Campaign ${result.campaign_id} saved for ${result.recipient_count} recipients.` });
      setBody('');
      setPhonesText('');
    } catch (err) {
      setStatus({ type: 'error', text: err.message });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <h2>Create campaign</h2>
          <p className="muted">Message content and recipients are provided by the tenant, not hardcoded.</p>
        </div>
      </div>
      <form className="stack" onSubmit={submit}>
        <label>
          Message content
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows="6" placeholder="Enter campaign message content" required />
        </label>
        <label>
          Phone numbers
          <textarea value={phonesText} onChange={(e) => setPhonesText(e.target.value)} rows="5" placeholder="One number per line, or separated by comma/semicolon" required />
        </label>
        <label>
          Send date and time
          <input value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} type="datetime-local" required />
        </label>
		<div className="consent">
		  <input
			id="campaign-consent"
			type="checkbox"
			checked={acceptedTerms}
			onChange={(e) => setAcceptedTerms(e.target.checked)}
		  />
		  <label htmlFor="campaign-consent">
			I confirm that I have a lawful basis to contact these recipients and agree to the{' '}
			<a
			  href="https://www.proactiveit.pl/en/dialoterms"
			  target="_blank"
			  rel="noopener noreferrer"
			>
			  Terms of Service
			</a>
			{' '}and{' '}
			<a
			  href="https://www.proactiveit.pl/en/privacy-policy"
			  target="_blank"
			  rel="noopener noreferrer"
			>
			  Privacy Policy
			</a>.
		  </label>
		</div>
        <div className="form-footer">
          <span className="muted">Recipients: {phones.length}</span>
          <button className="primary" 
			disabled={
			  loading ||
			  !body.trim() ||
			  phones.length === 0 ||
			  !acceptedTerms
			}
		    type="submit">
            {loading ? 'Saving…' : 'Save campaign'}
          </button>
        </div>
        {status && <div className={`alert ${status.type}`}>{status.text}</div>}
      </form>
    </section>
  );
}

function BarChart({ data }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="chart" role="img" aria-label="Monthly metrics bar chart">
      {data.map((item) => (
        <div className="bar-row" key={item.name}>
          <span className="bar-label">{METRIC_LABELS[item.name] || item.name}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${Math.max(2, (item.value / max) * 100)}%` }} />
          </div>
          <span className="bar-value">{item.value}</span>
        </div>
      ))}
    </div>
  );
}

function MetricsPanel() {
  const [month, setMonth] = useState(currentMonth());
  const [metrics, setMetrics] = useState({});
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    setStatus(null);
    try {
      const result = await getMonthlyMetrics(month);
      setMetrics(result.metrics || {});
    } catch (err) {
      setStatus({ type: 'error', text: err.message });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const chartData = Object.entries(metrics).map(([name, value]) => ({ name, value: Number(value || 0) }));

  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <h2>Monthly statistics</h2>
          <p className="muted">Aggregate tenant metrics without PII.</p>
        </div>
        <div className="inline-controls">
          <input value={month} onChange={(e) => setMonth(e.target.value)} type="month" />
          <button className="secondary" onClick={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
        </div>
      </div>
      {status && <div className={`alert ${status.type}`}>{status.text}</div>}
      {chartData.length ? <BarChart data={chartData} /> : <p className="muted">No metrics for selected month.</p>}
    </section>
  );
}

function tenantFromToken(session) {
  if (!session?.idToken) return null;

  const payload = JSON.parse(atob(session.idToken.split('.')[1]));
  return payload['custom:tenant_id'];
}

function Dashboard({ session, onLogout }) {
  const tokenTenantId = tenantFromToken(session);
  
  const hasAccess = tokenTenantId === TENANT_ID;
  
  if (!hasAccess) {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <h1>Invalid tenant</h1>
          <p className="muted">
            Your account does not have access to this tenant panel.
          </p>
          <button className="secondary" onClick={onLogout}>
            Log out
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="dashboard-shell">
      <header className="topbar">
		  <div className="topbar-left">
			<img
			  src="/logo.png"
			  alt=".Dialo"
			  className="topbar-logo"
			/>
			<div>
			  <p className="eyebrow">
				Tenant: {TENANT_ID}
			  </p>
			  <h2 className="welcome-title">
				Welcome, {session.email}
			  </h2>
			</div>
		  </div>
		  <button
			className="secondary"
			onClick={onLogout}
		  >
			Log out
		  </button>
		</header>
      <section className="welcome-card">
        <h2>Panel overview</h2>
        <p>Create outbound campaigns and review monthly bot statistics from your tenant-specific frontend.</p>
      </section>
      <div className="grid">
        <CampaignForm />
        <MetricsPanel />
      </div>
    </main>
  );
}

function App() {
  const [session, setSession] = useState(getSession());
  if (!session) return <LoginScreen onLogin={setSession} />;
  return <Dashboard session={session} onLogout={() => { logout(); setSession(null); }} />;
}

createRoot(document.getElementById('root')).render(<App />);
