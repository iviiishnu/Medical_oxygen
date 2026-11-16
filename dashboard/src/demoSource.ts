// DEMO mode: a simulated tablet so the dashboard can be shown without a backend connection.
// Steady ~5.4 kg/cm2 with a slow leak + recovery every 12 minutes; everything stays in the browser.
import type { Alert, Device, Point } from './logic.ts';
import type { DataSource } from './source.ts';

const LOW = 3.5, CRIT = 3.0, CYCLE = 15 * 60_000, MIN = 60_000;

/** One incident shape starting at p=0: leak 0.8/min for 3 min, 1 min low, 2 min recovery. */
function incident(p: number): number | null {
  if (p < 0 || p >= 6 * MIN) return null;
  if (p < 3 * MIN) return 5.4 - (p / MIN) * 0.8;
  if (p < 4 * MIN) return 3.0;
  return 3.0 + ((p - 4 * MIN) / (2 * MIN)) * 2.4;
}

let T0 = Date.now();
const PAST_INCIDENTS = [-19.5 * 3600_000, -6.2 * 3600_000];      // two incidents in the last 24 h

function pressureAt(t: number): number {
  const noise = Math.sin(t / 7000) * 0.03 + Math.sin(t / 2300) * 0.02 + Math.sin(t / 3.6e6) * 0.08;
  for (const s of PAST_INCIDENTS) {
    const v = incident(t - (T0 + s));
    if (v != null) return v + noise;
  }
  if (t > T0 + 2 * MIN) {                                       // live: an incident every 15 min
    const v = incident((t - T0 - 2 * MIN) % CYCLE);
    if (v != null) return v + noise;
  }
  return 5.4 + noise;
}

export function demoSource(): DataSource {
  const t0 = Date.now();
  T0 = t0;
  const history: Point[] = [];
  for (let t = t0 - 24 * 3600_000; t <= t0; t += 60_000) {
    const v = pressureAt(t);
    history.push({ t, v: Math.round(v * 100) / 100, status: v < CRIT ? 'CRITICAL' : v < LOW ? 'LOW' : 'OK' });
  }
  // a 20-minute camera outage in the night, to show the gap
  for (const p of history) if (p.t > t0 - 9 * 3600_000 && p.t < t0 - 9 * 3600_000 + 20 * 60_000) p.v = null;

  const alerts: Alert[] = [];
  let open: Alert | null = null;
  const subsA = new Set<(a: Alert[]) => void>();
  const subsD = new Set<(d: Device[]) => void>();
  const subsH = new Set<(p: Point[]) => void>();
  let lastAlarm = 'OK';
  const user = 'nurse.station@demo';

  function device(now: number): Device {
    const v = pressureAt(now);
    const alarm = v < CRIT ? 'CRITICAL' : v < LOW ? 'LOW' : 'OK';
    const falling = pressureAt(now) - pressureAt(now - 30_000) < -0.25;
    return {
      id: 'tab-main-o2-01', name: 'Main O2 panel (DEMO)', value: Math.round(v * 100) / 100, unit: 'kg/cm2',
      status: alarm, alarm, trendFalling: falling, lastHeartbeatMs: now, online: true,
      battery: 100, lowThreshold: LOW, criticalThreshold: CRIT,
    };
  }

  function step() {
    const now = Date.now();
    const d = device(now);
    if (d.alarm !== lastAlarm) {
      if (open && open.state !== 'RESOLVED') { open.state = 'RESOLVED'; open.resolvedMs = now; }
      if (d.alarm !== 'OK') {
        open = { id: `demo-${now}`, type: d.alarm, state: 'OPEN', deviceId: d.id, value: d.value, unit: 'kg/cm2',
          createdMs: now, ackedBy: null, ackedMs: null, resolvedMs: null, escalationLevel: 0 };
        alerts.unshift(open);
      } else open = null;
      lastAlarm = d.alarm;
    }
    if (now - history[history.length - 1].t >= 60_000) history.push({ t: now, v: d.value, status: d.status });
    subsD.forEach(cb => cb([d]));
    subsA.forEach(cb => cb([...alerts]));
    subsH.forEach(cb => cb([...history]));
  }
  setInterval(step, 2000);

  return {
    mode: 'demo',
    signedIn: () => true,
    userName: () => user,
    async signIn() {},
    async restoreSession() { return true; },
    onDevices(cb) { subsD.add(cb); step(); return () => subsD.delete(cb); },
    onAlerts(cb) { subsA.add(cb); cb([...alerts]); return () => subsA.delete(cb); },
    onHistory(_id, cb) { subsH.add(cb); cb([...history]); return () => subsH.delete(cb); },
    async acknowledge(id) {
      const a = alerts.find(x => x.id === id);
      if (a && a.state === 'OPEN') { a.state = 'ACKED'; a.ackedBy = user; a.ackedMs = Date.now(); }
      subsA.forEach(cb => cb([...alerts]));
    },
  };
}
