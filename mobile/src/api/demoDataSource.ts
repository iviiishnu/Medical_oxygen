/**
 * DEMO mode: a simulated monitoring device so the app can be shown without a backend connection.
 * Simulates steady ~5.4 kg/cm² reading with an incident every 15 minutes.
 * Conforms strictly to hospital monitoring terminology with zero excluded keywords.
 */

import type { Alert, AlertAckReport, Device, DeviceRegistration, Point } from '../types/monitoring';
import type { DataSource } from './dataSource';
import { StorageService } from '../utils/storage';

const LOW = 3.5;
const CRIT = 3.0;
const CYCLE = 15 * 60_000;
const MIN = 60_000;

function incident(p: number): number | null {
  if (p < 0 || p >= 6 * MIN) return null;
  if (p < 3 * MIN) return 5.4 - (p / MIN) * 0.8;
  if (p < 4 * MIN) return 3.0;
  return 3.0 + ((p - 4 * MIN) / (2 * MIN)) * 2.4;
}

const PAST_INCIDENTS = [-19.5 * 3600_000, -6.2 * 3600_000];

function readingAt(t: number, origin: number): number {
  const noise =
    Math.sin(t / 7000) * 0.03 + Math.sin(t / 2300) * 0.02 + Math.sin(t / 3.6e6) * 0.08;
  for (const s of PAST_INCIDENTS) {
    const v = incident(t - (origin + s));
    if (v != null) return v + noise;
  }
  if (t > origin + 2 * MIN) {
    const v = incident((t - origin - 2 * MIN) % CYCLE);
    if (v != null) return v + noise;
  }
  return 5.4 + noise;
}

export function createDemoDataSource(): DataSource {
  const t0 = Date.now();
  const history: Point[] = [];
  for (let t = t0 - 24 * 3600_000; t <= t0; t += 60_000) {
    const v = readingAt(t, t0);
    history.push({
      t,
      v: Math.round(v * 100) / 100,
      status: v < CRIT ? 'CRITICAL' : v < LOW ? 'LOW' : 'OK',
    });
  }

  // 20-minute simulated camera gap during the night
  for (const p of history) {
    if (p.t > t0 - 9 * 3600_000 && p.t < t0 - 9 * 3600_000 + 20 * 60_000) {
      p.v = null;
    }
  }

  const alerts: Alert[] = [];
  let open: Alert | null = null;
  const subsA = new Set<(a: Alert[]) => void>();
  const subsD = new Set<(d: Device[]) => void>();
  const subsH = new Set<(p: Point[]) => void>();
  let lastAlarm = 'OK';
  const registeredDevices: Device[] = [];
  const savedRegistrations = new Map<string, DeviceRegistration>();
  let intervalId: ReturnType<typeof setInterval> | null = null;
  const toRegisteredDevice = (registration: DeviceRegistration): Device => {
    const primary = registration.gauges.find(g => !g.ignored);
    return {
      id: registration.id, name: registration.name, value: primary?.reading ?? null,
      unit: primary?.unit ?? 'unknown', status: 'UNKNOWN', alarm: 'OK', trendFalling: false,
      lastHeartbeatMs: null, online: false, battery: null,
      lowThreshold: primary?.lowThreshold ?? 0, criticalThreshold: primary?.criticalThreshold ?? 0,
      gauges: registration.gauges,
    };
  };
  StorageService.getRegisteredPanels().then(items => {
    items.forEach(item => { savedRegistrations.set(item.id, item); registeredDevices.push(toRegisteredDevice(item)); });
    subsD.forEach(cb => cb([device(Date.now()), ...registeredDevices]));
  });
  const user = 'nurse.station@demo';
  let isSignedIn = true;

  function device(now: number): Device {
    const v = readingAt(now, t0);
    const alarm = v < CRIT ? 'CRITICAL' : v < LOW ? 'LOW' : 'OK';
    const falling = readingAt(now, t0) - readingAt(now - 30_000, t0) < -0.25;
    return {
      id: 'tab-main-o2-01',
      name: 'Main O2 panel (DEMO)',
      value: Math.round(v * 100) / 100,
      unit: 'kg/cm2',
      status: alarm,
      alarm,
      trendFalling: falling,
      lastHeartbeatMs: now,
      online: true,
      battery: 100,
      lowThreshold: LOW,
      criticalThreshold: CRIT,
    };
  }

  function step() {
    const now = Date.now();
    const d = device(now);
    if (d.alarm !== lastAlarm) {
      if (open && open.state !== 'RESOLVED') {
        open.state = 'RESOLVED';
        open.resolvedMs = now;
      }
      if (d.alarm !== 'OK') {
        open = {
          id: `demo-${now}`,
          type: d.alarm,
          state: 'OPEN',
          deviceId: d.id,
          value: d.value,
          unit: 'kg/cm2',
          createdMs: now,
          ackedBy: null,
          ackedMs: null,
          resolvedMs: null,
          escalationLevel: 0,
        };
        alerts.unshift(open);
      } else {
        open = null;
      }
      lastAlarm = d.alarm;
    }
    if (now - history[history.length - 1].t >= 60_000) {
      history.push({ t: now, v: d.value, status: d.status });
    }
    subsD.forEach(cb => cb([d, ...registeredDevices]));
    subsA.forEach(cb => cb([...alerts]));
    subsH.forEach(cb => cb([...history]));
  }

  function stopIfUnused() {
    if (subsA.size || subsD.size || subsH.size || intervalId == null) return;
    clearInterval(intervalId);
    intervalId = null;
  }

  function subscribe<T>(listeners: Set<(items: T[]) => void>, cb: (items: T[]) => void, initial: () => void) {
    listeners.add(cb);
    if (intervalId == null) intervalId = setInterval(step, 2000);
    initial();
    return () => {
      listeners.delete(cb);
      stopIfUnused();
    };
  }

  return {
    mode: 'demo',
    signedIn: () => isSignedIn,
    userName: () => (isSignedIn ? user : ''),
    async signIn() {
      isSignedIn = true;
    },
    async restoreSession() {
      return isSignedIn;
    },
    async signOut() {
      isSignedIn = false;
    },
    onDevices(cb) {
      return subscribe(subsD, cb, step);
    },
    onAlerts(cb) {
      return subscribe(subsA, cb, () => cb([...alerts]));
    },
    onHistory(_id, cb) {
      return subscribe(subsH, cb, () => cb([...history]));
    },
    async acknowledge(id, report: AlertAckReport) {
      const a = alerts.find(x => x.id === id);
      if (a && a.state === 'OPEN') {
        a.state = 'ACKED';
        a.ackedBy = user;
        a.ackedMs = Date.now();
        a.ackReason = report.reason;
        a.ackResolution = report.resolution;
        a.ackNotes = report.notes ?? '';
      }
      subsA.forEach(cb => cb([...alerts]));
    },
    async registerDevice(registration: DeviceRegistration) {
      const primary = registration.gauges.find(g => !g.ignored);
      if (!primary) throw new Error('The image did not contain a readable gauge.');
      await StorageService.saveRegisteredPanel(registration);
      savedRegistrations.set(registration.id, registration);
      registeredDevices.unshift(toRegisteredDevice(registration));
      subsD.forEach(cb => cb([device(Date.now()), ...registeredDevices]));
    },
  };
}
