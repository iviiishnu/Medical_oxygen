'use strict';
// Pure decision logic for the Cloud Functions (no Firebase imports -> unit-testable).

const DEFAULTS = Object.freeze({
  escalation_after_s: 120,   // unacknowledged for this long -> next tier
  heartbeat_s: 30,
  missed_heartbeats: 2,      // TABLET_OFFLINE after this many missed heartbeats
  grace_s: 5,
});

const ALERT_TYPES = ['LOW', 'CRITICAL', 'UNCERTAIN', 'MONITORING_LOST', 'TABLET_OFFLINE', 'TREND_FALLING'];
const SEVERITY = { CRITICAL: 5, LOW: 4, MONITORING_LOST: 4, TABLET_OFFLINE: 4, UNCERTAIN: 3, TREND_FALLING: 2 };

function toMillis(ts) {
  if (ts == null) return null;
  if (typeof ts === 'number') return ts;
  if (typeof ts.toMillis === 'function') return ts.toMillis();
  if (ts instanceof Date) return ts.getTime();
  const t = Date.parse(ts);
  return Number.isNaN(t) ? null : t;
}

/**
 * Staff to notify at an escalation level.
 * Level 0 = on-duty staff with the lowest escalation_order; every level adds the next tier.
 * Staff with no FCM token are skipped (they still see the dashboard).
 */
function pickRecipients(staff, level) {
  const onDuty = staff.filter(s => s.on_duty && Array.isArray(s.fcm_tokens) && s.fcm_tokens.length > 0);
  const tiers = [...new Set(onDuty.map(s => s.escalation_order ?? 99))].sort((a, b) => a - b);
  if (tiers.length === 0) return { recipients: [], maxLevel: 0 };
  const lvl = Math.min(level, tiers.length - 1);
  const maxOrder = tiers[lvl];
  return { recipients: onDuty.filter(s => (s.escalation_order ?? 99) <= maxOrder), maxLevel: tiers.length - 1 };
}

/** Should this OPEN alert be (re-)notified at a higher level now? Returns the new level or null. */
function escalationDue(alert, nowMs, cfg = DEFAULTS) {
  if (alert.state !== 'OPEN') return null;
  const last = toMillis(alert.last_notified_at) ?? toMillis(alert.created_at);
  if (last == null) return 0;
  if (nowMs - last < cfg.escalation_after_s * 1000) return null;
  return (alert.escalation_level ?? 0) + 1;
}

/** Device considered offline when the last heartbeat is older than missed*interval + grace. */
function isOffline(device, nowMs, cfg = DEFAULTS) {
  const hb = toMillis(device.last_heartbeat);
  const interval = (device.config && device.config.heartbeat_s) || cfg.heartbeat_s;
  if (hb == null) return true;
  return nowMs - hb > (cfg.missed_heartbeats * interval + cfg.grace_s) * 1000;
}

function alertTitle(type) {
  return {
    CRITICAL: 'CRITICAL: oxygen pressure very low',
    LOW: 'LOW oxygen pressure',
    MONITORING_LOST: 'Oxygen monitor cannot read the gauge',
    TABLET_OFFLINE: 'Oxygen monitor tablet OFFLINE',
    UNCERTAIN: 'Oxygen reading uncertain - check panel',
    TREND_FALLING: 'Oxygen pressure falling fast',
  }[type] || `Oxygen alert: ${type}`;
}

/**
 * FCM message. Data-only + android priority "high" so the app's messaging service runs even
 * when the app is closed and can show the full-screen alarm on its loud channel.
 */
function buildAlertMessage(alertId, alert, tokens, level) {
  const value = alert.value == null ? '' : String(alert.value);
  const title = alertTitle(alert.type);
  const body = value ? `${alert.gauge_id || 'oxygen'}: ${value} ${alert.unit || 'kg/cm2'}` : String(alert.reason || 'Check the oxygen monitoring panel.');
  return {
    tokens,
    // A notification payload is required for Android/iOS to show a system notification
    // while the app is backgrounded or terminated. Keep data for foreground routing too.
    notification: { title, body },
    data: {
      kind: 'ALERT',
      alert_id: alertId,
      type: String(alert.type),
      device_id: String(alert.device_id || ''),
      gauge_id: String(alert.gauge_id || ''),
      value,
      unit: String(alert.unit || 'kg/cm2'),
      title,
      body,
      level: String(level),
      severity: String(SEVERITY[alert.type] || 3),
      created_at: String(toMillis(alert.created_at) || ''),
    },
    android: {
      priority: 'high', ttl: 10 * 60 * 1000,
      notification: { sound: 'default', priority: 'high', visibility: 'public' },
    },
    apns: {
      headers: { 'apns-priority': '10' },
      payload: { aps: { alert: { title, body }, sound: 'default', 'content-available': 1 } },
    },
  };
}

function buildUpdateMessage(alertId, alert, tokens) {
  return {
    tokens,
    data: {
      kind: 'ALERT_UPDATE',
      alert_id: alertId,
      state: String(alert.state),
      acked_by_name: String(alert.acked_by_name || ''),
    },
    android: { priority: 'high', ttl: 10 * 60 * 1000 },
  };
}

/** Tokens FCM reported as dead -> remove them from staff docs. */
const DEAD_TOKEN_CODES = new Set([
  'messaging/registration-token-not-registered',
  'messaging/invalid-registration-token',
  'messaging/invalid-argument',
]);

function deadTokens(tokens, batchResponse) {
  const dead = [];
  (batchResponse.responses || []).forEach((r, i) => {
    if (!r.success && r.error && DEAD_TOKEN_CODES.has(r.error.code)) dead.push(tokens[i]);
  });
  return dead;
}

module.exports = {
  DEFAULTS, ALERT_TYPES, SEVERITY, toMillis, pickRecipients, escalationDue, isOffline,
  alertTitle, buildAlertMessage, buildUpdateMessage, deadTokens,
};
