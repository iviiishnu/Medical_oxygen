/**
 * api/portal.js
 * =============
 * Typed wrappers for every backend portal endpoint.
 * All functions use the shared api client so the Bearer token is attached
 * automatically and 401s trigger a logout redirect.
 */
import { api } from './client';

/** GET /api/summary → { devices: {...}, alerts: {...} } */
export function getSummary() {
  return api.get('/api/summary');
}

/** GET /api/devices → array of device objects */
export function getDevices() {
  return api.get('/api/devices');
}

/**
 * GET /api/alerts
 * @param {string} status  "active" | "acknowledged" | "resolved" | "all"  (default "active")
 */
export function getAlerts(status = 'active') {
  return api.get(`/api/alerts?status=${encodeURIComponent(status)}`);
}

/** GET /api/alerts/:id */
export function getAlert(id) {
  return api.get(`/api/alerts/${id}`);
}

/**
 * POST /api/alerts/:id/acknowledge
 * @param {number} id
 * @param {string} note  optional note
 */
export function acknowledgeAlert(id, note = '') {
  return api.post(`/api/alerts/${id}/acknowledge`, { note: note || null });
}

/**
 * POST /api/alerts/:id/resolve
 * @param {number} id
 * @param {string} note  optional note
 */
export function resolveAlert(id, note = '') {
  return api.post(`/api/alerts/${id}/resolve`, { note: note || null });
}

/**
 * GET /api/devices/:deviceId/readings
 * @param {string} deviceId
 * @param {string|null} gas      e.g. "OXYGEN" — omit for all gases
 * @param {number}       minutes  default 60
 */
export function getReadings(deviceId, gas = null, minutes = 60) {
  const params = new URLSearchParams({ minutes });
  if (gas) params.set('gas', gas);
  return api.get(`/api/devices/${encodeURIComponent(deviceId)}/readings?${params}`);
}

/** GET /api/activity → last 15 activity log entries */
export function getActivity() {
  return api.get('/api/activity');
}

/**
 * PATCH /api/devices/:id
 * @param {string} deviceId
 * @param {{ name?: string, location?: string }} patch
 */
export function updateDevice(deviceId, patch) {
  return api.patch(`/api/devices/${encodeURIComponent(deviceId)}`, patch);
}

// ── Incidents ─────────────────────────────────────────────────────────────────

/** GET /api/incidents?status=open|in_progress|closed|all */
export function getIncidents(status = 'open') {
  return api.get(`/api/incidents?status=${encodeURIComponent(status)}`);
}

/** GET /api/incidents/:id */
export function getIncident(id) {
  return api.get(`/api/incidents/${id}`);
}

/** POST /api/incidents */
export function createIncident(body) {
  return api.post('/api/incidents', body);
}

/** PATCH /api/incidents/:id */
export function patchIncident(id, patch) {
  return api.patch(`/api/incidents/${id}`, patch);
}

/** POST /api/incidents/:id/notes */
export function addIncidentNote(id, note) {
  return api.post(`/api/incidents/${id}/notes`, { note });
}

// ── Analytics ───────────────────────────────────────────────────────────────

/**
 * GET /api/analytics?from=<ISO>&to=<ISO>
 * @param {string} fromIso
 * @param {string} toIso
 */
export function getAnalytics(fromIso, toIso) {
  const params = new URLSearchParams({ from: fromIso, to: toIso });
  return api.get(`/api/analytics?${params}`);
}

/**
 * Download a CSV export (alerts / incidents / readings).
 * Fetches with the Bearer token (a plain <a href> would not send it),
 * then saves the response as a blob.
 *
 * @param {'alerts'|'incidents'|'readings'} kind
 * @param {string} fromIso
 * @param {string} toIso
 * @returns {Promise<void>}  resolves on success; throws on failure
 */
export async function downloadCsv(kind, fromIso, toIso) {
  const token = (() => {
    try { return sessionStorage.getItem('medigas_token'); } catch { return null; }
  })();
  const params = new URLSearchParams({ from: fromIso, to: toIso });
  const res = await fetch(`/api/export/${kind}.csv?${params}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent('medigas:logout'));
    throw new Error('Session expired. Please log in again.');
  }
  if (!res.ok) throw new Error(`Export failed (HTTP ${res.status})`);

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${kind}-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}


// ── User Management ─────────────────────────────────────────────────────────

/** GET /api/users → array of user objects (admin only) */
export function getUsers() {
  return api.get('/api/users');
}

/** POST /api/users — create a new user (admin only) */
export function createUser(body) {
  return api.post('/api/users', body);
}

/** PATCH /api/users/:id — update name/email/role/is_active (admin only) */
export function patchUser(id, patch) {
  return api.patch(`/api/users/${id}`, patch);
}

// ── Auth — Change Password ──────────────────────────────────────────────────

/** POST /auth/change-password — change own password */
export function changePassword(current_password, new_password) {
  return api.post('/auth/change-password', { current_password, new_password });
}
