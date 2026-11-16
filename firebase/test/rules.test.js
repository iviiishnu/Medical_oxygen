'use strict';
// Security-rules tests. Run: npm run test:rules (starts the Firestore emulator).
const test = require('node:test');
const fs = require('fs');
const path = require('path');
const { initializeTestEnvironment, assertSucceeds, assertFails } = require('@firebase/rules-unit-testing');
const { doc, getDoc, setDoc, updateDoc, addDoc, collection, serverTimestamp, deleteDoc } = require('firebase/firestore');

let env;
const DEV = 'tab-main-o2-01';

test.before(async () => {
  env = await initializeTestEnvironment({
    projectId: 'o2-monitor-demo',
    firestore: { rules: fs.readFileSync(path.join(__dirname, '..', 'firestore.rules'), 'utf8') },
  });
});
test.after(async () => { await env.cleanup(); });
test.beforeEach(async () => {
  await env.clearFirestore();
  await env.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore();
    await setDoc(doc(db, `devices/${DEV}`), { gauge_id: 'oxygen_main', config: { low_threshold: 3.5 } });
    await setDoc(doc(db, 'alerts/a1'), { device_id: DEV, type: 'LOW', state: 'OPEN' });
    await setDoc(doc(db, 'staff/nurse'), { name: 'N', on_duty: true, escalation_order: 1, fcm_tokens: [] });
  });
});

const tablet = () => env.authenticatedContext('tabletUid', { role: 'device', device_id: DEV }).firestore();
const otherTablet = () => env.authenticatedContext('t2', { role: 'device', device_id: 'other' }).firestore();
const nurse = () => env.authenticatedContext('nurse', { role: 'staff' }).firestore();
const admin = () => env.authenticatedContext('boss', { role: 'admin' }).firestore();
const stranger = () => env.authenticatedContext('x', {}).firestore();
const anon = () => env.unauthenticatedContext().firestore();

test('tablet writes its readings and heartbeat', async () => {
  await assertSucceeds(addDoc(collection(tablet(), `devices/${DEV}/readings`), { device_id: DEV, value: 5 }));
  await assertSucceeds(updateDoc(doc(tablet(), `devices/${DEV}`), { last_heartbeat: serverTimestamp(), status: 'OK' }));
});

test('tablet cannot change its own thresholds or online flag', async () => {
  await assertFails(updateDoc(doc(tablet(), `devices/${DEV}`), { config: { low_threshold: 0 } }));
  await assertFails(updateDoc(doc(tablet(), `devices/${DEV}`), { online: true }));
  await assertSucceeds(updateDoc(doc(tablet(), `devices/${DEV}`), { calibration: '{"center":[1,2]}' }));
});

test('another tablet cannot write here', async () => {
  await assertFails(addDoc(collection(otherTablet(), `devices/${DEV}/readings`), { device_id: DEV, value: 5 }));
  await assertFails(updateDoc(doc(otherTablet(), `devices/${DEV}`), { status: 'OK' }));
});

test('readings are append-only', async () => {
  await env.withSecurityRulesDisabled(async (ctx) => setDoc(doc(ctx.firestore(), `devices/${DEV}/readings/r1`), { device_id: DEV, value: 5 }));
  await assertFails(updateDoc(doc(tablet(), `devices/${DEV}/readings/r1`), { value: 9 }));
  await assertFails(deleteDoc(doc(admin(), `devices/${DEV}/readings/r1`)));
});

test('tablet creates OPEN alerts only for itself', async () => {
  await assertSucceeds(addDoc(collection(tablet(), 'alerts'), { device_id: DEV, type: 'LOW', state: 'OPEN' }));
  await assertFails(addDoc(collection(tablet(), 'alerts'), { device_id: 'other', type: 'LOW', state: 'OPEN' }));
  await assertFails(addDoc(collection(tablet(), 'alerts'), { device_id: DEV, type: 'LOW', state: 'ACKED' }));
});

test('staff acknowledge with their own uid and server time', async () => {
  await assertSucceeds(updateDoc(doc(nurse(), 'alerts/a1'), {
    state: 'ACKED', acked_by: 'nurse', acked_by_name: 'N', acked_at: serverTimestamp(),
    ack_reason: 'Supply interruption', ack_resolution: 'Supply restored', ack_notes: '',
  }));
});

test('staff cannot ack as someone else, or rewrite the alert', async () => {
  await assertFails(updateDoc(doc(nurse(), 'alerts/a1'), { state: 'ACKED', acked_by: 'someone', acked_at: serverTimestamp() }));
  await assertFails(updateDoc(doc(nurse(), 'alerts/a1'), { state: 'ACKED', acked_by: 'nurse', acked_at: serverTimestamp(), value: 9 }));
  await assertFails(updateDoc(doc(nurse(), 'alerts/a1'), { state: 'RESOLVED' }));
  await assertFails(deleteDoc(doc(admin(), 'alerts/a1')));
});

test('tablet resolves its own alert', async () => {
  await assertSucceeds(updateDoc(doc(tablet(), 'alerts/a1'), { state: 'RESOLVED', resolved_at: serverTimestamp() }));
});

test('strangers and anonymous users see nothing', async () => {
  for (const db of [stranger(), anon()]) {
    await assertFails(getDoc(doc(db, `devices/${DEV}`)));
    await assertFails(getDoc(doc(db, 'alerts/a1')));
    await assertFails(getDoc(doc(db, 'staff/nurse')));
  }
});

test('staff can register a phone but not promote themselves', async () => {
  await assertSucceeds(updateDoc(doc(nurse(), 'staff/nurse'), { fcm_tokens: ['tok'], on_duty: false }));
  await assertFails(updateDoc(doc(nurse(), 'staff/nurse'), { escalation_order: 0 }));
  await assertFails(updateDoc(doc(nurse(), 'staff/nurse'), { role: 'admin' }));
});

test('admin manages devices and staff', async () => {
  await assertSucceeds(updateDoc(doc(admin(), `devices/${DEV}`), { config: { low_threshold: 3.6 } }));
  await assertSucceeds(setDoc(doc(admin(), 'staff/new'), { name: 'New', on_duty: true, escalation_order: 2 }));
});
