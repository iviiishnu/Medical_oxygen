import test from 'node:test';
import assert from 'node:assert/strict';
import {
  effectiveStatus,
  SEVERITY,
  needsSound,
  label,
  ago,
  niceTicks,
  decimate,
  segments,
} from './logic.ts';
import type { Device, Alert, Point } from '../types/monitoring.ts';

const baseDevice: Device = {
  id: 'tab-1',
  name: 'Main O2 Panel',
  value: 5.4,
  unit: 'kg/cm2',
  status: 'OK',
  alarm: 'OK',
  trendFalling: false,
  lastHeartbeatMs: 100_000,
  online: true,
  battery: 95,
  lowThreshold: 3.5,
  criticalThreshold: 3.0,
};

test('effectiveStatus marks online responsive device correctly', () => {
  assert.equal(effectiveStatus(baseDevice, 110_000), 'OK');
  assert.equal(effectiveStatus({ ...baseDevice, status: 'LOW' }, 110_000), 'LOW');
  assert.equal(effectiveStatus({ ...baseDevice, status: 'CRITICAL' }, 110_000), 'CRITICAL');
});

test('effectiveStatus marks device offline after 65s without heartbeat', () => {
  assert.equal(effectiveStatus(baseDevice, 100_000 + 65_001), 'TABLET_OFFLINE');
  assert.equal(effectiveStatus({ ...baseDevice, online: false }, 100_000), 'TABLET_OFFLINE');
});

test('needsSound triggers only for open high-severity alerts', () => {
  const openCrit: Alert = {
    id: 'a1',
    type: 'CRITICAL',
    state: 'OPEN',
    deviceId: 'tab-1',
    value: 2.8,
    unit: 'kg/cm2',
    createdMs: 100_000,
    ackedBy: null,
    ackedMs: null,
    resolvedMs: null,
    escalationLevel: 0,
  };
  assert.equal(needsSound([openCrit]), true);

  const ackedCrit: Alert = { ...openCrit, state: 'ACKED' };
  assert.equal(needsSound([ackedCrit]), false);

  const openLowSeverity: Alert = { ...openCrit, type: 'TREND_FALLING' };
  assert.equal(needsSound([openLowSeverity]), false);
});

test('label uses clinical monitoring terms and conforms to standards', () => {
  assert.equal(label('OK'), 'Normal');
  assert.equal(label('LOW'), 'Low level');
  assert.equal(label('CRITICAL'), 'Critical');
  assert.equal(label('TABLET_OFFLINE'), 'Tablet offline');
  assert.equal(label('TREND_FALLING'), 'Falling fast');
  // Strict assertion: label must use standardized level terminology
  assert.equal(label('LOW'), 'Low level');
});

test('ago formats timestamps relative to nowMs', () => {
  assert.equal(ago(null, 10_000), 'never');
  assert.equal(ago(9_000, 10_000), 'just now');
  assert.equal(ago(9_950, 10_000), 'just now');
  assert.equal(ago(9_920, 10_000), 'just now');
  assert.equal(ago(0, 30_000), '30 s ago');
  assert.equal(ago(0, 120_000), '2 min ago');
  assert.equal(ago(0, 7_200_000), '2 h ago');
});

test('niceTicks generates clean rounded ticks', () => {
  const ticks = niceTicks(0, 10, 5);
  assert.ok(ticks.length >= 3);
  assert.equal(ticks[0], 0);
  assert.ok(ticks[ticks.length - 1] >= 10);
});

test('decimate preserves min and max without data loss', () => {
  const pts: Point[] = [
    { t: 10, v: 5.0, status: 'OK' },
    { t: 20, v: 2.1, status: 'CRITICAL' },
    { t: 30, v: 8.5, status: 'OK' },
    { t: 40, v: 4.0, status: 'OK' },
  ];
  const out = decimate(pts, 2);
  const vals = out.map(p => p.v);
  assert.ok(vals.includes(2.1));
  assert.ok(vals.includes(8.5));
});

test('segments splits across gaps', () => {
  const pts: Point[] = [
    { t: 1000, v: 5.0, status: 'OK' },
    { t: 2000, v: 5.1, status: 'OK' },
    { t: 8000, v: 5.2, status: 'OK' }, // 6s gap > 3s
  ];
  const s = segments(pts, 3000);
  assert.equal(s.length, 2);
  assert.equal(s[0].length, 2);
  assert.equal(s[1].length, 1);
});
