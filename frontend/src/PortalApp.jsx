/**
 * PortalApp.jsx
 * =============
 * Top-level app for the Oxygen Flow Check portal.
 * Manages data via usePortalData, renders the shell + route pages,
 * and shows global alert toasts (top-right, 10 s).
 */
import { useEffect, useRef } from 'react';
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { usePortalData } from './hooks/usePortalData';
import { PortalShell }   from './components/layout/PortalShell';

// Pages
import PortalDashboard from './pages/PortalDashboard';
import LiveMonitoring  from './pages/LiveMonitoring';
import AlertsPage      from './pages/PortalAlerts';
import Incidents       from './pages/Incidents';
import { Analytics }   from './pages/Analytics';
import Settings        from './pages/Settings';

import AlertToastItem  from './components/ui/AlertToast';

// ── Beep helper ───────────────────────────────────────────────────────────────
// Generates a short 880 Hz tone via the Web Audio API.
// Falls back silently if the API is unavailable.
// Respects the localStorage toggle (medigas_notif_sound).
function playBeep() {
  try {
    const SOUND_KEY = 'medigas_notif_sound';
    const pref = localStorage.getItem(SOUND_KEY);
    if (pref === 'off') return;                       // user turned it off
    const ctx  = new (window.AudioContext || window.webkitAudioContext)();
    const osc  = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type      = 'sine';
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    gain.gain.setValueAtTime(0.25, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.4);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.4);
  } catch {}
}

// ── Browser notification helper ───────────────────────────────────────────────
function showBrowserNotification(title, body) {
  try {
    const BROWSER_KEY = 'medigas_notif_browser';
    if (localStorage.getItem(BROWSER_KEY) !== 'on') return;
    if (typeof Notification === 'undefined') return;
    if (Notification.permission !== 'granted') return;
    new Notification(title, { body });
  } catch {}
}

export default function PortalApp() {
  const {
    summary, devices, alerts, activity,
    loading, connected,
    toasts, dismissToast,
    acknowledgeAlert, resolveAlert,
  } = usePortalData();

  return (
    <>
      <PortalShell summary={summary} alerts={alerts} connected={connected}>
        <Routes>
          <Route path="/"           element={<PortalDashboard summary={summary} devices={devices} alerts={alerts} activity={activity} loading={loading} />} />
          <Route path="/live"       element={<LiveMonitoring devices={devices} loading={loading} />} />
          <Route path="/alerts"     element={
            <AlertsPage
              alerts={alerts}
              onAcknowledge={acknowledgeAlert}
              onResolve={resolveAlert}
            />
          } />
          <Route path="/incidents"  element={<Incidents />} />
          <Route path="/analytics"  element={<Analytics />} />
          <Route path="/settings"   element={<Settings wsConnected={connected} summary={summary} />} />
          <Route path="*"           element={<Navigate to="/" replace />} />
        </Routes>
      </PortalShell>

      {/* Global alert toasts — top-right, 10 s */}
      <AlertToastStack toasts={toasts} onDismiss={dismissToast} />
    </>
  );
}

/** Renders alert toasts at the top-right corner of the viewport. */
function AlertToastStack({ toasts, onDismiss }) {
  const navigate     = useNavigate();
  const prevCountRef = useRef(0);

  // Play beep + browser notification whenever a new danger toast is added
  useEffect(() => {
    const dangerCount = toasts.filter(t => t.type === 'danger').length;
    if (dangerCount > prevCountRef.current) {
      playBeep();
      // Fire browser notification for the newest danger toast
      const newest = toasts[0];
      if (newest && newest.type === 'danger') {
        showBrowserNotification('New Critical Alert', newest.message || 'A new alert has been raised');
      }
    }
    prevCountRef.current = dangerCount;
  }, [toasts]);

  if (!toasts.length) return null;

  return (
    <div className="fixed top-5 right-5 z-[9999] flex flex-col gap-2 items-end pointer-events-none">
      {toasts.map(t => (
        <div key={t.id} className="pointer-events-auto">
          <AlertToastItem
            toast={t}
            onDismiss={onDismiss}
            onAction={t.action ? () => { onDismiss(t.id); navigate(t.action.href); } : undefined}
          />
        </div>
      ))}
    </div>
  );
}
