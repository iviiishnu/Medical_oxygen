'use strict';
/**
 * Cloud Functions - the "second layer". The tablet already sounds its own alarm;
 * these fan alerts out to phones, escalate, and watch the tablet's heartbeat.
 *
 *  onAlertCreated   alerts/{id} created by the tablet -> FCM to tier-0 on-duty staff
 *  onAlertUpdated   ACKED / RESOLVED -> tell every notified phone to stop ringing
 *  escalate         every minute: OPEN alerts not acknowledged in time -> next tier
 *  heartbeatWatch   every minute: 2 missed heartbeats -> TABLET_OFFLINE alert
 *  onDeviceUpdated  heartbeat back -> device online again, TABLET_OFFLINE resolved
 */
const { initializeApp } = require('firebase-admin/app');
const { getFirestore, FieldValue, Timestamp } = require('firebase-admin/firestore');
const { getMessaging } = require('firebase-admin/messaging');
const { onDocumentCreated, onDocumentUpdated } = require('firebase-functions/v2/firestore');
const { onSchedule } = require('firebase-functions/v2/scheduler');
const { setGlobalOptions, logger } = require('firebase-functions/v2');
const L = require('./lib/logic');

initializeApp();
setGlobalOptions({ region: 'asia-south1', maxInstances: 5 });
const db = getFirestore();

async function loadSettings() {
  const snap = await db.doc('settings/alerting').get();
  return { ...L.DEFAULTS, ...(snap.exists ? snap.data() : {}) };
}

async function loadStaff() {
  const snap = await db.collection('staff').where('on_duty', '==', true).get();
  return snap.docs.map(d => ({ uid: d.id, ...d.data() }));
}

const EMULATED_FCM = process.env.FUNCTIONS_EMULATOR === 'true' && !process.env.REAL_FCM;

async function send(message) {
  if (!message.tokens.length) return { successCount: 0, failureCount: 0, responses: [] };
  if (EMULATED_FCM) {
    // the emulator cannot deliver pushes: record them so tests can assert on them
    await db.collection('_emulator_outbox').add({ ...message, at: FieldValue.serverTimestamp() });
    return { successCount: message.tokens.length, failureCount: 0, responses: message.tokens.map(() => ({ success: true })) };
  }
  let res;
  try {
    res = await getMessaging().sendEachForMulticast(message);
  } catch (e) {
    // never let a push failure stop the alert bookkeeping / escalation
    logger.error('FCM send failed', { code: e.code, message: e.message });
    return { successCount: 0, failureCount: message.tokens.length, responses: [], error: String(e.code || e.message) };
  }
  const dead = L.deadTokens(message.tokens, res);
  if (dead.length) {
    const staff = await db.collection('staff').where('fcm_tokens', 'array-contains-any', dead.slice(0, 30)).get();
    await Promise.all(staff.docs.map(d => d.ref.update({ fcm_tokens: FieldValue.arrayRemove(...dead) })));
    logger.warn('removed dead FCM tokens', { count: dead.length });
  }
  return res;
}

async function notify(alertRef, alert, level) {
  const staff = await loadStaff();
  const { recipients, maxLevel } = L.pickRecipients(staff, level);
  const tokens = [...new Set(recipients.flatMap(s => s.fcm_tokens))];
  const res = await send(L.buildAlertMessage(alertRef.id, alert, tokens, level));
  await alertRef.update({
    escalation_level: Math.min(level, maxLevel),
    last_notified_at: FieldValue.serverTimestamp(),
    notified_uids: FieldValue.arrayUnion(...recipients.map(r => r.uid), '_'),
    notify_log: FieldValue.arrayUnion({
      at: Timestamp.now(), level, uids: recipients.map(r => r.uid),
      ok: res.successCount, failed: res.failureCount,
    }),
  });
  if (!recipients.length) logger.error('NO on-duty staff with a phone registered!', { alert: alertRef.id });
  return res;
}

exports.onAlertCreated = onDocumentCreated('alerts/{alertId}', async (event) => {
  const alert = event.data.data();
  if (alert.state !== 'OPEN') return;
  await notify(event.data.ref, alert, 0);
});

exports.onAlertUpdated = onDocumentUpdated('alerts/{alertId}', async (event) => {
  const before = event.data.before.data();
  const after = event.data.after.data();
  if (before.state === after.state || after.state === 'OPEN') return;
  const uids = (after.notified_uids || []).filter(u => u !== '_');
  if (!uids.length) return;
  const docs = await Promise.all(uids.map(u => db.doc(`staff/${u}`).get()));
  const tokens = [...new Set(docs.filter(d => d.exists).flatMap(d => d.data().fcm_tokens || []))];
  await send(L.buildUpdateMessage(event.params.alertId, after, tokens));
});

async function runEscalation(now = Date.now()) {
  const cfg = await loadSettings();
  const open = await db.collection('alerts').where('state', '==', 'OPEN').get();
  let n = 0;
  for (const doc of open.docs) {
    const level = L.escalationDue(doc.data(), now, cfg);
    if (level != null) {
      logger.info('escalating', { alert: doc.id, level });
      await notify(doc.ref, doc.data(), level);
      n++;
    }
  }
  return n;
}

async function runHeartbeatWatch(now = Date.now()) {
  const cfg = await loadSettings();
  const devices = await db.collection('devices').get();
  let n = 0;
  for (const d of devices.docs) {
    const dev = d.data();
    if (dev.enabled === false) continue;
    if (L.isOffline(dev, now, cfg) && dev.online !== false) {
      await db.runTransaction(async (tx) => {
        const fresh = await tx.get(d.ref);
        if (fresh.data().online === false) return;              // another run got here first
        tx.update(d.ref, { online: false, offline_since: FieldValue.serverTimestamp() });
        tx.create(db.collection('alerts').doc(), {
          type: 'TABLET_OFFLINE', state: 'OPEN', source: 'server',
          device_id: d.id, gauge_id: dev.gauge_id || '', value: null, unit: 'kg/cm2',
          reason: `no heartbeat since ${dev.last_heartbeat ? L.toMillis(dev.last_heartbeat) : 'never'}`,
          created_at: FieldValue.serverTimestamp(), escalation_level: 0,
        });
      });
      logger.warn('TABLET_OFFLINE', { device: d.id });
      n++;
    }
  }
  return n;
}

exports.escalate = onSchedule({ schedule: 'every 1 minutes', timeZone: 'Asia/Kolkata' }, () => runEscalation());
exports.heartbeatWatch = onSchedule({ schedule: 'every 1 minutes', timeZone: 'Asia/Kolkata' }, () => runHeartbeatWatch());

// Emulator-only HTTP hooks so tests can run the scheduled jobs with a fake clock.
if (process.env.FUNCTIONS_EMULATOR === 'true') {
  const { onRequest } = require('firebase-functions/v2/https');
  exports.testRunJobs = onRequest(async (req, res) => {
    const now = Number(req.query.now || Date.now());
    res.json({ escalated: await runEscalation(now), offline: await runHeartbeatWatch(now) });
  });
}

exports.onDeviceUpdated = onDocumentUpdated('devices/{deviceId}', async (event) => {
  const before = event.data.before.data();
  const after = event.data.after.data();
  const hbBefore = L.toMillis(before.last_heartbeat);
  const hbAfter = L.toMillis(after.last_heartbeat);
  if (after.online === false && hbAfter && hbAfter !== hbBefore && !L.isOffline(after, Date.now())) {
    await event.data.after.ref.update({ online: true, offline_since: FieldValue.delete() });
    const open = await db.collection('alerts')
      .where('device_id', '==', event.params.deviceId)
      .where('type', '==', 'TABLET_OFFLINE')
      .where('state', 'in', ['OPEN', 'ACKED']).get();
    await Promise.all(open.docs.map(a => a.ref.update({
      state: 'RESOLVED', resolved_at: FieldValue.serverTimestamp(), resolve_value: 'heartbeat_back',
    })));
  }
});
