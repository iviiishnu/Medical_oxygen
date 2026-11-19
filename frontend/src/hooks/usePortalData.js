/**
 * hooks/usePortalData.js
 * ======================
 * Loads summary, devices, active alerts, and activity.
 * Reloads automatically whenever the WebSocket sends
 * { type: "reading" } or { type: "alert" }.
 *
 * Returns the raw data plus helper callbacks for alert actions.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useWebSocket } from './useWebSocket';
import {
  getSummary,
  getDevices,
  getAlerts,
  getActivity,
  acknowledgeAlert as apiAcknowledge,
  resolveAlert     as apiResolve,
} from '../api/portal';

export function usePortalData() {
  const [summary,   setSummary]   = useState(null);
  const [devices,   setDevices]   = useState([]);
  const [alerts,    setAlerts]    = useState([]);    // active alerts
  const [activity,  setActivity]  = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);

  // Toast state: [{ id, type, message, action?, alertObj? }]
  const [toasts, setToasts] = useState([]);

  // Track known active alert ids; null = first load (no toast on initial fetch)
  const knownIdsRef = useRef(null);

  // ── Toast helpers ─────────────────────────────────────────────────────────
  const pushToast = useCallback((type, message, action = null, alertObj = null) => {
    const id = Date.now() + Math.random();
    setToasts(t => [{ id, type, message, action, alertObj }, ...t].slice(0, 5));
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 10000);
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts(t => t.filter(x => x.id !== id));
  }, []);

  // ── Load everything ───────────────────────────────────────────────────────
  const reload = useCallback(async () => {
    try {
      setError(null);
      const [summaryData, devicesData, alertsData, activityData] = await Promise.all([
        getSummary(),
        getDevices(),
        getAlerts('active'),
        getActivity(),
      ]);
      setSummary(summaryData);
      setDevices(devicesData);

      const incoming = alertsData || [];

      if (knownIdsRef.current !== null) {
        // Find alerts whose id wasn't in the previous set
        const newAlerts = incoming.filter(a => !knownIdsRef.current.has(a.id));
        newAlerts.forEach(a => {
          // Build a readable message: "CRITICAL: tab-01 oxygen 2.5 kg/cm2"
          const severity = a.severity || a.alert_type || 'ALERT';
          const gauges   = a.gauges || [];
          let detail     = a.device_id;
          if (gauges.length > 0) {
            const g = gauges[0];
            detail = `${a.device_id} ${(g.gas || '').toLowerCase()} ${g.reading != null ? g.reading : ''} ${g.unit || ''}`.trim();
          } else if (a.worst_status) {
            detail = `${a.device_id} — ${a.worst_status}`;
          }
          pushToast('danger', `${severity}: ${detail}`, { label: 'View', href: '/alerts' }, a);
        });
      }

      // Update known ids (first load just seeds the set, no toasts)
      knownIdsRef.current = new Set(incoming.map(a => a.id));

      setAlerts(incoming);
      setActivity(activityData || []);
    } catch (e) {
      setError(e.message || 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, [pushToast]);

  // Initial load
  useEffect(() => { reload(); }, [reload]);

  // ── WebSocket ─────────────────────────────────────────────────────────────
  const handleWsMessage = useCallback((evt) => {
    let msg;
    try { msg = JSON.parse(evt.data); } catch { return; }
    const { type } = msg;
    if (type === 'reading' || type === 'alert') {
      reload();
    }
  }, [reload]);

  const { connected } = useWebSocket(handleWsMessage);

  // ── Alert actions ─────────────────────────────────────────────────────────
  const acknowledgeAlert = useCallback(async (id, note = '') => {
    try {
      await apiAcknowledge(id, note);
      await reload();
      pushToast('info', 'Alert acknowledged');
    } catch (e) {
      pushToast('danger', `Failed: ${e.message}`);
    }
  }, [reload, pushToast]);

  const resolveAlert = useCallback(async (id, note = '') => {
    try {
      await apiResolve(id, note);
      await reload();
      pushToast('success', 'Alert resolved');
    } catch (e) {
      pushToast('danger', `Failed: ${e.message}`);
    }
  }, [reload, pushToast]);

  return {
    summary,
    devices,
    alerts,
    activity,
    loading,
    error,
    connected,
    reload,
    toasts,
    pushToast,
    dismissToast,
    acknowledgeAlert,
    resolveAlert,
  };
}
