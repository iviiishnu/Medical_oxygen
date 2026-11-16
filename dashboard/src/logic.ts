// Pure helpers (unit-tested in logic.test.ts).

export type Status = 'OK' | 'LOW' | 'CRITICAL' | 'UNCERTAIN' | 'MONITORING_LOST' | 'TABLET_OFFLINE' | 'UNKNOWN';

export interface Device {
  id: string;
  name: string;
  value: number | null;
  unit: string;
  status: string;
  alarm: string;
  trendFalling: boolean;
  lastHeartbeatMs: number | null;
  online: boolean;
  battery: number | null;
  lowThreshold: number;
  criticalThreshold: number;
}

export interface Alert {
  id: string;
  type: string;
  state: 'OPEN' | 'ACKED' | 'RESOLVED' | string;
  deviceId: string;
  value: number | null;
  unit: string;
  createdMs: number | null;
  ackedBy: string | null;
  ackedMs: number | null;
  resolvedMs: number | null;
  escalationLevel: number;
}

export interface Point { t: number; v: number | null; status: string }

export const OFFLINE_AFTER_MS = 65_000;   // 2 missed 30 s heartbeats + grace (same as API watchdog)

/** What the desk should show for a device, given the time now. Never "OK" for a silent tablet. */
export function effectiveStatus(d: Device, nowMs: number): Status {
  if (!d.online || d.lastHeartbeatMs == null || nowMs - d.lastHeartbeatMs > OFFLINE_AFTER_MS) return 'TABLET_OFFLINE';
  const s = d.status as Status;
  return (['OK', 'LOW', 'CRITICAL', 'UNCERTAIN', 'MONITORING_LOST'] as string[]).includes(s) ? s : 'UNKNOWN';
}

export const SEVERITY: Record<string, number> = {
  CRITICAL: 5, LOW: 4, MONITORING_LOST: 4, TABLET_OFFLINE: 4, UNCERTAIN: 3, TREND_FALLING: 2, OK: 0, UNKNOWN: 1,
};

export function needsSound(alerts: Alert[]): boolean {
  return alerts.some(a => a.state === 'OPEN' && (SEVERITY[a.type] ?? 3) >= 3);
}

export function label(s: string): string {
  return ({
    OK: 'Normal', LOW: 'Low pressure', CRITICAL: 'Critical', UNCERTAIN: 'Reading uncertain',
    MONITORING_LOST: 'Monitoring lost', TABLET_OFFLINE: 'Tablet offline', TREND_FALLING: 'Falling fast',
    UNKNOWN: 'Unknown',
  } as Record<string, string>)[s] ?? s;
}

export function ago(ms: number | null, nowMs: number): string {
  if (ms == null) return 'never';
  const s = Math.round((nowMs - ms) / 1000);
  if (s < 5) return 'just now';
  if (s < 90) return `${s} s ago`;
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  return `${Math.round(s / 3600)} h ago`;
}

/** Round-number axis ticks covering [lo, hi]. */
export function niceTicks(lo: number, hi: number, target = 5): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / target;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) ?? 10 * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v * 1e6) / 1e6);
  return out;
}

/** Downsample to at most n points per bucket using min/max so dips are never hidden. */
export function decimate(points: Point[], maxPoints: number): Point[] {
  if (points.length <= maxPoints) return points;
  const bucket = Math.ceil(points.length / (maxPoints / 2));
  const out: Point[] = [];
  for (let i = 0; i < points.length; i += bucket) {
    const chunk = points.slice(i, i + bucket).filter(p => p.v != null);
    if (!chunk.length) { out.push({ ...points[i], v: null }); continue; }
    let mn = chunk[0], mx = chunk[0];
    for (const p of chunk) { if (p.v! < mn.v!) mn = p; if (p.v! > mx.v!) mx = p; }
    if (mn === mx) out.push(mn);
    else out.push(...(mn.t < mx.t ? [mn, mx] : [mx, mn]));
  }
  return out;
}

/** Split a series into line segments at gaps (no data for longer than gapMs). */
export function segments(points: Point[], gapMs: number): Point[][] {
  const segs: Point[][] = [];
  let cur: Point[] = [];
  let last: number | null = null;
  for (const p of points) {
    if (p.v == null || (last != null && p.t - last > gapMs)) {
      if (cur.length) segs.push(cur);
      cur = [];
    }
    if (p.v != null) { cur.push(p); last = p.t; }
  }
  if (cur.length) segs.push(cur);
  return segs;
}
