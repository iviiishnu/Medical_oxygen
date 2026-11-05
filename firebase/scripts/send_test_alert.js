#!/usr/bin/env node
'use strict';
/**
 * Phase 0 test: write a fake LOW reading + OPEN alert, and push a high-priority alarm to a phone.
 *
 *   # real project (service account JSON from Firebase console > Project settings > Service accounts)
 *   set GOOGLE_APPLICATION_CREDENTIALS=C:\keys\o2-monitor-sa.json
 *   node scripts/send_test_alert.js --token <FCM token shown in the app's Settings screen>
 *
 *   # local emulator (Firestore only, push is printed instead of sent)
 *   set FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
 *   node scripts/send_test_alert.js --project o2-monitor-demo
 *
 * Without --token the Cloud Function onAlertCreated sends the push to on-duty staff instead.
 */
const path = require('path');
const fnDir = path.join(__dirname, '..', 'functions');
const { initializeApp } = require(require.resolve('firebase-admin/app', { paths: [fnDir] }));
const { getFirestore, FieldValue } = require(require.resolve('firebase-admin/firestore', { paths: [fnDir] }));
const { getMessaging } = require(require.resolve('firebase-admin/messaging', { paths: [fnDir] }));
const L = require('../functions/lib/logic');

function arg(name, def) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : def;
}

async function main() {
  const project = arg('project', process.env.GCLOUD_PROJECT || undefined);
  initializeApp(project ? { projectId: project } : undefined);
  const db = getFirestore();
  const device = arg('device', 'tab-main-o2-01');
  const value = Number(arg('value', '3.1'));
  const type = arg('type', 'LOW');
  const now = new Date();

  const reading = {
    device_id: device, gauge_id: 'oxygen_main', ts: now.toISOString(), value, unit: 'kg/cm2',
    confidence: 0.95, lamp_state: 'LOW', method_agree: true, status: type,
    server_ts: FieldValue.serverTimestamp(), expire_at: new Date(now.getTime() + 30 * 864e5), test: true,
  };
  await db.doc(`devices/${device}`).set({ gauge_id: 'oxygen_main', name: 'TEST tablet' }, { merge: true });
  await db.collection(`devices/${device}/readings`).add(reading);
  const alertRef = await db.collection('alerts').add({
    type, state: 'OPEN', device_id: device, gauge_id: 'oxygen_main', value, unit: 'kg/cm2',
    created_at: FieldValue.serverTimestamp(), escalation_level: 0, test: true, source: 'test_script',
  });
  console.log('wrote reading + alert', alertRef.id);

  const token = arg('token');
  if (!token) {
    console.log('no --token: onAlertCreated (if deployed / emulated) will notify on-duty staff');
    return;
  }
  const msg = L.buildAlertMessage(alertRef.id, { type, value, device_id: device, gauge_id: 'oxygen_main', created_at: now.getTime() }, [token], 0);
  if (process.env.FIRESTORE_EMULATOR_HOST) {
    console.log('emulator mode - FCM payload that would be sent:\n', JSON.stringify(msg, null, 2));
    return;
  }
  const res = await getMessaging().sendEachForMulticast(msg);
  console.log(`push: ${res.successCount} ok, ${res.failureCount} failed`);
  res.responses.forEach(r => { if (!r.success) console.error(' ', r.error.code, r.error.message); });
  process.exitCode = res.failureCount ? 1 : 0;
}

main().catch(e => { console.error(e); process.exit(1); });
