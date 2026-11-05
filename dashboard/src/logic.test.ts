import test from 'node:test';
import assert from 'node:assert/strict';
import { effectiveStatus, needsSound, niceTicks, decimate, segments, type Device, type Point } from './logic.ts';

const base: Device = {
  id: 'tab', name: 'Main O2', value: 5.4, unit: 'kg/cm2', status: 'OK', alarm: 'OK', trendFalling: false,
  lastHeartbeatMs: 1_000_000, online: true, battery: 90, lowThreshold: 3.5, criticalThreshold: 3,
};

test('a silent tablet is never shown as OK', () => {
  assert.equal(effectiveStatus(base, 1_000_000 + 30_000), 'OK');
  assert.equal(effectiveStatus(base, 1_000_000 + 66_000), 'TABLET_OFFLINE');
  assert.equal(effectiveStatus({ ...base, lastHeartbeatMs: null }, 0), 'TABLET_OFFLINE');
  assert.equal(effectiveStatus({ ...base, online: false }, 1_000_000), 'TABLET_OFFLINE');
  assert.equal(effectiveStatus({ ...base, status: 'weird' }, 1_000_000), 'UNKNOWN');
});

test('sound only for open, serious alerts', () => {
  const a = { id: '1', type: 'LOW', state: 'OPEN', deviceId: 'tab', value: 3, unit: 'kg/cm2', createdMs: 0,
    ackedBy: null, ackedMs: null, resolvedMs: null, escalationLevel: 0 };
  assert.equal(needsSound([a]), true);
  assert.equal(needsSound([{ ...a, state: 'ACKED' }]), false);
  assert.equal(needsSound([{ ...a, type: 'TREND_FALLING' }]), false);
  assert.equal(needsSound([]), false);
});

test('nice ticks', () => {
  assert.deepEqual(niceTicks(0, 8, 4), [0, 2, 4, 6, 8]);
  assert.deepEqual(niceTicks(2.3, 6.1, 4), [3, 4, 5, 6]);
  assert.deepEqual(niceTicks(0, 16), [0, 5, 10, 15]);
});

test('decimation keeps the dip', () => {
  const pts: Point[] = Array.from({ length: 1440 }, (_, i) => ({ t: i * 60_000, v: i === 700 ? 1.0 : 5.4, status: 'OK' }));
  const d = decimate(pts, 300);
  assert.ok(d.length <= 320);
  assert.ok(d.some(p => p.v === 1.0), 'minimum must survive decimation');
});

test('segments split at gaps and nulls', () => {
  const pts: Point[] = [
    { t: 0, v: 5, status: 'OK' }, { t: 60_000, v: 5, status: 'OK' },
    { t: 600_000, v: 5, status: 'OK' }, { t: 660_000, v: null, status: 'X' }, { t: 720_000, v: 4, status: 'OK' },
  ];
  assert.equal(segments(pts, 180_000).length, 3);
});
