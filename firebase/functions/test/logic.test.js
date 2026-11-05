'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const L = require('../lib/logic');

const staff = [
  { uid: 'a', on_duty: true, escalation_order: 1, fcm_tokens: ['ta'] },
  { uid: 'b', on_duty: true, escalation_order: 1, fcm_tokens: ['tb'] },
  { uid: 'c', on_duty: true, escalation_order: 2, fcm_tokens: ['tc'] },
  { uid: 'd', on_duty: false, escalation_order: 1, fcm_tokens: ['td'] },
  { uid: 'e', on_duty: true, escalation_order: 3, fcm_tokens: [] },
  { uid: 'f', on_duty: true, escalation_order: 5, fcm_tokens: ['tf'] },
];

test('level 0 notifies the first tier only', () => {
  const r = L.pickRecipients(staff, 0);
  assert.deepEqual(r.recipients.map(s => s.uid), ['a', 'b']);
  assert.equal(r.maxLevel, 2);
});

test('each level adds the next tier, skipping tiers with no phones', () => {
  assert.deepEqual(L.pickRecipients(staff, 1).recipients.map(s => s.uid), ['a', 'b', 'c']);
  assert.deepEqual(L.pickRecipients(staff, 2).recipients.map(s => s.uid), ['a', 'b', 'c', 'f']);
  assert.deepEqual(L.pickRecipients(staff, 9).recipients.map(s => s.uid), ['a', 'b', 'c', 'f']);
});

test('no staff -> empty, never throws', () => {
  assert.deepEqual(L.pickRecipients([], 0), { recipients: [], maxLevel: 0 });
});

test('escalation timing', () => {
  const t0 = 1_000_000;
  const a = { state: 'OPEN', escalation_level: 0, last_notified_at: t0 };
  assert.equal(L.escalationDue(a, t0 + 119_000), null);
  assert.equal(L.escalationDue(a, t0 + 120_000), 1);
  assert.equal(L.escalationDue({ ...a, state: 'ACKED' }, t0 + 999_000), null);
  assert.equal(L.escalationDue({ state: 'OPEN', created_at: t0 }, t0 + 121_000), 1);
  assert.equal(L.escalationDue({ state: 'OPEN' }, t0), 0);
});

test('offline after two missed heartbeats (+grace)', () => {
  const now = 10_000_000;
  assert.equal(L.isOffline({ last_heartbeat: now - 30_000 }, now), false);
  assert.equal(L.isOffline({ last_heartbeat: now - 65_000 }, now), false);
  assert.equal(L.isOffline({ last_heartbeat: now - 65_001 }, now), true);
  assert.equal(L.isOffline({}, now), true);
  assert.equal(L.isOffline({ last_heartbeat: { toMillis: () => now - 10_000 } }, now), false);
  assert.equal(L.isOffline({ last_heartbeat: new Date(now - 100_000).toISOString() }, now), true);
});

test('FCM message is data-only, high priority, all strings', () => {
  const m = L.buildAlertMessage('x1', { type: 'LOW', value: 3.2, device_id: 'tab', gauge_id: 'oxygen_main', created_at: 5 }, ['t'], 0);
  assert.equal(m.android.priority, 'high');
  assert.equal(m.notification, undefined);
  for (const v of Object.values(m.data)) assert.equal(typeof v, 'string');
  assert.match(m.data.title, /LOW/);
  assert.equal(m.data.body, 'oxygen_main: 3.2 kg/cm2');
});

test('null value alert body falls back to reason', () => {
  const m = L.buildAlertMessage('x', { type: 'TABLET_OFFLINE', value: null, reason: 'no heartbeat' }, [], 0);
  assert.equal(m.data.value, '');
  assert.equal(m.data.body, 'no heartbeat');
});

test('dead tokens extracted', () => {
  const res = { responses: [
    { success: true },
    { success: false, error: { code: 'messaging/registration-token-not-registered' } },
    { success: false, error: { code: 'messaging/internal-error' } },
  ] };
  assert.deepEqual(L.deadTokens(['a', 'b', 'c'], res), ['b']);
});
