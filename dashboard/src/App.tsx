import { useEffect, useState } from 'react';
import { HistoryChart } from './HistoryChart.tsx';
import { ago, effectiveStatus, label, needsSound, type Alert, type Device, type Point } from './logic.ts';
import { audioReady, setAlarm, unlockAudio } from './sound.ts';
import type { DataSource } from './source.ts';

const ICON: Record<string, string> = {
  OK: '✓', LOW: '▼', CRITICAL: '⛔', UNCERTAIN: '?', MONITORING_LOST: '⚠', TABLET_OFFLINE: '⚠',
  TREND_FALLING: '↘', UNKNOWN: '•',
};
const statusClass = (s: string) => `st-${s.toLowerCase()}`;

function useNow(ms = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), ms); return () => clearInterval(t); }, [ms]);
  return now;
}

function StatusBadge({ s }: { s: string }) {
  return <span className={`badge ${statusClass(s)}`}><span aria-hidden>{ICON[s] ?? '•'}</span> {label(s)}</span>;
}

function Login({ src, onDone }: { src: DataSource; onDone: () => void }) {
  const [email, setEmail] = useState('');
  const [pw, setPw] = useState('');
  const [err, setErr] = useState('');
  return (
    <form className="login" onSubmit={async e => {
      e.preventDefault();
      try { await src.signIn(email, pw); onDone(); } catch (x) { setErr(String((x as Error).message)); }
    }}>
      <h1>Oxygen Monitor</h1>
      <p className="muted">Nursing station dashboard. Sign in with your staff account.</p>
      <input placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="username" />
      <input placeholder="Password" type="password" value={pw} onChange={e => setPw(e.target.value)} autoComplete="current-password" />
      <button type="submit">Sign in</button>
      {err && <p className="error">{err}</p>}
    </form>
  );
}

function DevicePanel({ d, src, now }: { d: Device; src: DataSource; now: number }) {
  const [hist, setHist] = useState<Point[]>([]);
  const [table, setTable] = useState(false);
  useEffect(() => src.onHistory(d.id, setHist), [src, d.id]);
  const s = effectiveStatus(d, now);
  return (
    <section className={`panel ${statusClass(s)}-edge`}>
      <header className="panel-head">
        <div>
          <h2>{d.name}</h2>
          <div className="muted">{d.id} · updated {ago(d.lastHeartbeatMs, now)}{d.battery != null && ` · battery ${Math.round(d.battery)}%`}</div>
        </div>
        <StatusBadge s={s} />
      </header>
      <div className="hero">
        <span className={`hero-num ${s === 'TABLET_OFFLINE' ? 'stale' : ''}`}>{d.value == null ? '--' : d.value.toFixed(2)}</span>
        <span className="hero-unit">{d.unit.replace('cm2', 'cm²')}</span>
        {d.trendFalling && <StatusBadge s="TREND_FALLING" />}
      </div>
      <div className="muted small">LOW below {d.lowThreshold} · CRITICAL below {d.criticalThreshold} {d.unit.replace('cm2', 'cm²')}</div>
      <div className="chart-head">
        <h3>Last 24 hours</h3>
        <button className="link" onClick={() => setTable(!table)}>{table ? 'Show chart' : 'Show table'}</button>
      </div>
      {table ? (
        <div className="table-scroll">
          <table>
            <thead><tr><th>Time</th><th className="num">Pressure</th><th>Status</th></tr></thead>
            <tbody>
              {[...hist].reverse().slice(0, 300).map(p => (
                <tr key={p.t}><td>{new Date(p.t).toLocaleString()}</td>
                  <td className="num">{p.v == null ? '—' : p.v.toFixed(2)}</td><td>{p.status}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <HistoryChart points={hist} low={d.lowThreshold} critical={d.criticalThreshold} unit={d.unit} nowMs={now} />}
    </section>
  );
}

export function App({ src }: { src: DataSource }) {
  const [authed, setAuthed] = useState(src.signedIn());
  const [devices, setDevices] = useState<Device[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [sound, setSound] = useState(audioReady());
  const [ackErr, setAckErr] = useState('');
  const now = useNow();

  useEffect(() => {
    if (!authed) return;
    const a = src.onDevices(setDevices);
    const b = src.onAlerts(setAlerts);
    return () => { a(); b(); };
  }, [src, authed]);

  // an offline tablet is an alarm at the desk even before the server's alert arrives
  const offline = devices.filter(d => effectiveStatus(d, now) === 'TABLET_OFFLINE');
  const ringing = needsSound(alerts) || offline.length > 0;
  useEffect(() => { setAlarm(ringing && sound); }, [ringing, sound]);
  useEffect(() => {
    document.title = ringing ? '⚠ ALARM - Oxygen Monitor' : 'Oxygen Monitor';
  }, [ringing]);

  if (!authed) return <Login src={src} onDone={() => setAuthed(true)} />;
  const open = alerts.filter(a => a.state === 'OPEN');

  const acknowledgeWithReport = (alertId: string) => {
    const reason = window.prompt('Brief reason for this alert:', 'Reading crossed its configured threshold');
    if (!reason?.trim()) return;
    const resolution = window.prompt('How was it resolved?', 'Checked the panel and restored the supply');
    if (!resolution?.trim()) return;
    src.acknowledge(alertId, { reason: reason.trim(), resolution: resolution.trim() })
      .catch(e => setAckErr(String(e.message)));
  };

  return (
    <div className={`app ${ringing ? 'ringing' : ''}`}>
      <header className="top">
        <div>
          <h1>Oxygen supply</h1>
          <div className="muted">Monitoring aid on top of the hospital's alarm panel · {src.userName()}
            {src.mode === 'demo' && <strong className="demo"> · DEMO DATA</strong>}</div>
        </div>
        {!sound && <button onClick={() => setSound(unlockAudio())}>Enable alarm sound</button>}
      </header>

      {open.length > 0 && (
        <div className="banner" role="alert">
          {open.map(a => (
            <div key={a.id} className="banner-row">
              <StatusBadge s={a.type} />
              <span>{a.deviceId}{a.value != null && ` · ${a.value.toFixed(2)} ${a.unit.replace('cm2', 'cm²')}`} · {ago(a.createdMs, now)}
                {a.escalationLevel > 0 && ` · escalated (level ${a.escalationLevel})`}</span>
              <button onClick={() => acknowledgeWithReport(a.id)}>Acknowledge</button>
            </div>
          ))}
          {ackErr && <div className="error">{ackErr}</div>}
        </div>
      )}

      <main className="grid">
        {devices.length === 0 && <p className="muted">No tablets registered yet.</p>}
        {devices.map(d => <DevicePanel key={d.id} d={d} src={src} now={now} />)}
      </main>

      <section className="panel">
        <h2>Alert log (24 h)</h2>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Raised</th><th>Alert</th><th>Tablet</th><th className="num">Value</th><th>State</th><th>Acknowledged by</th><th>Cleared</th></tr></thead>
            <tbody>
              {alerts.length === 0 && <tr><td colSpan={7} className="muted">No alerts in the last 24 hours</td></tr>}
              {alerts.map(a => (
                <tr key={a.id}>
                  <td>{a.createdMs ? new Date(a.createdMs).toLocaleTimeString() : '…'}</td>
                  <td><StatusBadge s={a.type} /></td>
                  <td>{a.deviceId}</td>
                  <td className="num">{a.value == null ? '—' : a.value.toFixed(2)}</td>
                  <td>{a.state}</td>
                  <td>{a.ackedBy ? `${a.ackedBy} · ${a.ackedMs ? new Date(a.ackedMs).toLocaleTimeString() : ''}` : '—'}</td>
                  <td>{a.resolvedMs ? new Date(a.resolvedMs).toLocaleTimeString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
