'use strict';
// End-to-end Cloud Functions test on the emulators. Run: npm run test:e2e
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const fnDir = path.join(__dirname, '..', 'functions');
const { initializeApp } = require(require.resolve('firebase-admin/app', { paths: [fnDir] }));
const { getFirestore, Timestamp } = require(require.resolve('firebase-admin/firestore', { paths: [fnDir] }));

const PROJECT = 'o2-monitor-demo';
initializeApp({ projectId: PROJECT });
const db = getFirestore();
const JOBS = `http://127.0.0.1:5001/${PROJECT}/asia-south1/testRunJobs`;
const DEV = 'tab-e2e';

async function waitFor(fn, ms = 20000) {
  const t0 = Date.now();
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() - t0 > ms) throw new Error('timeout waiting for condition');
    await new Promise(r => setTimeout(r, 250));
  }
}
async function outbox(pred) {
  const s = await db.collection('_emulator_outbox').get();
  return s.docs.map(d => d.data()).filter(pred);
}
async function runJobs(now) {
  const r = await fetch(`${JOBS}?now=${now}`);
  assert.equal(r.status, 200);
  return r.json();
}

test.before(async () => {
  await db.doc('staff/a').set({ name: 'Nurse A', on_duty: true, escalation_order: 1, fcm_tokens: ['tok-a'] });
  await db.doc('staff/c').set({ name: 'Biomed C', on_duty: true, escalation_order: 2, fcm_tokens: ['tok-c'] });
  await db.doc('staff/z').set({ name: 'Off duty', on_duty: false, escalation_order: 1, fcm_tokens: ['tok-z'] });
  await db.doc(`devices/${DEV}`).set({ gauge_id: 'oxygen_main', online: true, last_heartbeat: Timestamp.now() });
});

test('alert -> push to tier 1 -> escalate to tier 2 -> ack stops phones', async () => {
  const ref = await db.collection('alerts').add({
    type: 'LOW', state: 'OPEN', device_id: DEV, gauge_id: 'oxygen_main', value: 3.2, unit: 'kg/cm2',
    created_at: Timestamp.now(),
  });
  const first = await waitFor(async () => (await outbox(m => m.data.alert_id === ref.id && m.data.kind === 'ALERT'))[0]);
  assert.deepEqual(first.tokens, ['tok-a']);
  assert.equal(first.android.priority, 'high');
  assert.equal(first.data.type, 'LOW');
  await waitFor(async () => (await ref.get()).data().last_notified_at);

  // not yet due
  let r = await runJobs(Date.now() + 30_000);
  assert.equal(r.escalated, 0);
  // 2 minutes without acknowledgement -> tier 2 added
  r = await runJobs(Date.now() + 125_000);
  assert.equal(r.escalated, 1);
  const second = (await outbox(m => m.data.alert_id === ref.id && m.data.level === '1'))[0];
  assert.deepEqual(second.tokens.sort(), ['tok-a', 'tok-c']);
  assert.equal((await ref.get()).data().escalation_level, 1);

  await ref.update({ state: 'ACKED', acked_by: 'a', acked_by_name: 'Nurse A', acked_at: Timestamp.now() });
  const upd = await waitFor(async () => (await outbox(m => m.data.alert_id === ref.id && m.data.kind === 'ALERT_UPDATE'))[0]);
  assert.equal(upd.data.state, 'ACKED');
  assert.deepEqual(upd.tokens.sort(), ['tok-a', 'tok-c']);
  await runJobs(Date.now() + 999_000);
  assert.equal((await ref.get()).data().escalation_level, 1, 'acked alerts never escalate');
  assert.equal((await outbox(m => m.data.alert_id === ref.id && m.data.level === '2')).length, 0);
});

test('missed heartbeats -> TABLET_OFFLINE once; heartbeat back -> resolved', async () => {
  // the fake-clock jobs in the previous test may already have marked it offline: start clean
  const old = await db.collection('alerts').where('type', '==', 'TABLET_OFFLINE').get();
  await Promise.all(old.docs.map(d => d.ref.delete()));
  await db.doc(`devices/${DEV}`).update({ last_heartbeat: Timestamp.fromMillis(Date.now() - 200_000), online: true });
  const r1 = await runJobs(Date.now());
  assert.equal(r1.offline, 1);
  const r2 = await runJobs(Date.now());
  assert.equal(r2.offline, 0, 'only one offline alert per outage');
  const q = () => db.collection('alerts').where('device_id', '==', DEV).where('type', '==', 'TABLET_OFFLINE').get();
  const alert = (await q()).docs[0];
  assert.equal(alert.data().state, 'OPEN');
  await waitFor(async () => (await outbox(m => m.data.alert_id === alert.id && m.data.kind === 'ALERT')).length);

  await db.doc(`devices/${DEV}`).update({ last_heartbeat: Timestamp.now() });
  await waitFor(async () => (await db.doc(`devices/${DEV}`).get()).data().online === true);
  await waitFor(async () => (await q()).docs[0].data().state === 'RESOLVED');
});

test('alert with nobody on duty is still recorded (never throws)', async () => {
  await db.doc('staff/a').update({ on_duty: false });
  await db.doc('staff/c').update({ on_duty: false });
  const ref = await db.collection('alerts').add({ type: 'CRITICAL', state: 'OPEN', device_id: DEV, value: 2.0, created_at: Timestamp.now() });
  await waitFor(async () => (await ref.get()).data().last_notified_at);
  assert.equal((await ref.get()).data().escalation_level, 0);
});
