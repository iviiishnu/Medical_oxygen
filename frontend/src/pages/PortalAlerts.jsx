/**
 * pages/PortalAlerts.jsx  (redesigned)
 * =====================================
 * Alerts page — per lead spec:
 *   • Tabs synced with ?status=
 *   • Priority-ordered table: Actions column (View + Live), Device links,
 *     numeric Reading column, live-ticking Duration
 *   • Full-height side-panel drawer: sticky header, scrollable body, sticky footer
 *   • VIEWER role hides Acknowledge/Resolve
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { useSearchParams, Link, useNavigate } from 'react-router-dom';
import {
  Bell, CheckCircle, Archive, Clock, ExternalLink,
  AlertTriangle, X, Info, ChevronRight, Monitor, FileText,
} from 'lucide-react';
import { getAlerts, getAlert, acknowledgeAlert, resolveAlert } from '../api/portal';
import { useAuth } from '../hooks/useAuth';
import { Skeleton }  from '../components/ui/Skeleton';

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────
const VALID_TABS = ['active', 'acknowledged', 'resolved', 'all'];
const CARD = { boxShadow: '0 4px 24px rgba(80,110,180,0.08)' };

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
function deriveStatus(a) {
  if (a.resolved_at || a.cleared_at) return 'resolved';
  if (a.acknowledged_at) return 'acknowledged';
  return 'active';
}

function safeDate(raw) {
  if (!raw) return null;
  const d = raw instanceof Date ? raw : new Date(raw);
  return isNaN(d.getTime()) ? null : d;
}

function fmtDateTime(raw) {
  const d = safeDate(raw);
  return d
    ? d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—';
}

function fmtTime(raw) {
  const d = safeDate(raw);
  return d ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '';
}

/** Compute elapsed time from a Date to now */
function elapsedFrom(d) {
  if (!d) return '—';
  const diff = Date.now() - d.getTime();
  if (diff < 0) return 'just now';
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

/** Build the reading string from an alert list row */
function alertReading(a) {
  // The list endpoint returns: reading (top-level), unit, worst_status
  if (a.reading != null && a.unit) return `${a.reading} ${a.unit}`;
  if (a.reading != null)           return String(a.reading);
  // Fall back to worst_status only if it looks numeric (some backends set it to a value)
  if (a.worst_status && /^\d/.test(String(a.worst_status))) return a.worst_status;
  return '—';
}

// ─────────────────────────────────────────────────────────────────────────────
// Badge components (shared by table and drawer)
// ─────────────────────────────────────────────────────────────────────────────
const SEVERITY_STYLES = {
  CRITICAL:   { bg: '#FEF2F2', color: '#EF4444' },
  HIGH:       { bg: '#FEF2F2', color: '#EF4444' },
  OFFLINE:    { bg: '#F4F7FC', color: '#6B7280' },
  UNREADABLE: { bg: '#FFFBEB', color: '#D97706' },
  MEDIUM:     { bg: '#FFFBEB', color: '#D97706' },
  LOW:        { bg: '#EFF6FF', color: '#2563EB' },
};

function SeverityBadge({ severity }) {
  if (!severity) return <span className="text-muted text-xs">—</span>;
  const s   = severity.toUpperCase();
  const cfg = SEVERITY_STYLES[s] || { bg: '#F4F7FC', color: '#6B7280' };
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold"
      style={{ background: cfg.bg, color: cfg.color }}>
      {s}
    </span>
  );
}

const STATUS_STYLES = {
  active:       { bg: '#FEF2F2', color: '#DC2626' },
  acknowledged: { bg: '#FFFBEB', color: '#D97706' },
  resolved:     { bg: '#F0FDF4', color: '#16A34A' },
};

function StatusBadge({ status }) {
  const cfg = STATUS_STYLES[status] || { bg: '#F4F7FC', color: '#6B7280' };
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold capitalize"
      style={{ background: cfg.bg, color: cfg.color }}>
      {status}
    </span>
  );
}

function severityBorderColor(sev) {
  if (!sev) return '#E2E8F0';
  const s = sev.toUpperCase();
  if (s === 'CRITICAL' || s === 'HIGH')       return '#EF4444';
  if (s === 'OFFLINE'  || s === 'UNREADABLE') return '#F59E0B';
  return '#94A3B8';
}

// ─────────────────────────────────────────────────────────────────────────────
// Live-ticking duration hook
// ─────────────────────────────────────────────────────────────────────────────
function useLiveDuration(raw, active) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(id);
  }, [active]);
  // tick is just used to trigger re-render; the actual value is computed fresh
  return elapsedFrom(safeDate(raw));
}

// ─────────────────────────────────────────────────────────────────────────────
// Note modal (Acknowledge / Resolve)
// ─────────────────────────────────────────────────────────────────────────────
function NoteModal({ title, hint, isAck, loading, onConfirm, onCancel }) {
  const [note, setNote] = useState('');
  const ref = useRef(null);
  useEffect(() => { ref.current?.focus(); }, []);

  // Close on Escape
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onCancel(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onCancel]);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={onCancel} aria-hidden="true" />
      <div className="relative bg-white rounded-2xl p-6 w-full max-w-md"
        style={{ boxShadow: '0 20px 60px rgba(0,0,0,0.20)' }}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-navy">{title}</h3>
          <button onClick={onCancel} className="p-1 rounded-lg text-muted hover:bg-slate-100 hover:text-navy transition-colors">
            <X size={16} />
          </button>
        </div>
        <p className="text-xs text-muted mb-3">{hint}</p>
        <textarea
          ref={ref}
          value={note}
          onChange={e => setNote(e.target.value)}
          placeholder="Enter a note…"
          rows={3}
          className="w-full px-3 py-2 text-sm rounded-xl border border-slate-200 bg-slate-50 outline-none focus:border-blue-400 resize-none"
        />
        {isAck && (
          <p className="mt-2 flex items-center gap-1.5 text-[11px] text-amber-600 font-medium">
            <Info size={12} /> Acknowledging does not change the device status.
          </p>
        )}
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onCancel}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-muted hover:bg-slate-100 transition-colors">
            Cancel
          </button>
          <button onClick={() => onConfirm(note)} disabled={loading}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-white disabled:opacity-60"
            style={{ background: '#2F80ED' }}>
            {loading ? 'Working…' : 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Pre-readings compact table
// ─────────────────────────────────────────────────────────────────────────────
function PreReadingsTable({ readings }) {
  if (!readings?.length) {
    return <p className="text-xs text-muted italic py-2">No readings recorded before this alert.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-100">
      <table className="w-full text-left text-xs border-collapse">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-100">
            <th className="px-3 py-2 font-bold text-muted">Time</th>
            <th className="px-3 py-2 font-bold text-muted">Gas</th>
            <th className="px-3 py-2 font-bold text-muted">Reading</th>
            <th className="px-3 py-2 font-bold text-muted">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {readings.map((r, i) => (
            <tr key={i} className="hover:bg-slate-50/60">
              <td className="px-3 py-2 font-mono text-[10px] text-muted">{fmtTime(r.timestamp)}</td>
              <td className="px-3 py-2 text-navy font-medium">{r.gas || '—'}</td>
              <td className="px-3 py-2 text-navy">
                {r.reading != null ? `${r.reading} ${r.unit || ''}`.trim() : '—'}
              </td>
              <td className="px-3 py-2">
                <span className="text-[10px] font-semibold text-muted">{r.status || '—'}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Alert detail panel (the drawer contents)
// ─────────────────────────────────────────────────────────────────────────────
function AlertDetailPanel({ alertId, canAct, onClose, onActionDone }) {
  const [detail,  setDetail]  = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);
  const [modal,   setModal]   = useState(null); // 'acknowledge' | 'resolve'
  const [acting,  setActing]  = useState(false);

  const load = useCallback(async () => {
    if (!alertId) return;
    setLoading(true);
    setError(null);
    try { setDetail(await getAlert(alertId)); }
    catch (e) { setError(e.message || 'Failed to load'); }
    finally { setLoading(false); }
  }, [alertId]);

  useEffect(() => { load(); }, [load]);

  async function handleAction(type, note) {
    setActing(true);
    try {
      if (type === 'acknowledge') await acknowledgeAlert(alertId, note);
      else                        await resolveAlert(alertId, note);
      setModal(null);
      await load();
      onActionDone(type);
    } catch (e) {
      setModal(null);
      onActionDone(type, e.message);
    } finally {
      setActing(false);
    }
  }

  const status  = detail ? deriveStatus(detail) : null;
  const reasons = Array.isArray(detail?.reasons) ? detail.reasons : [];

  // ── Loading / error states ──────────────────────────────────────────────
  if (loading) return (
    <div className="flex flex-col gap-4 p-6">
      <Skeleton className="h-20" />
      <Skeleton className="h-14" />
      <Skeleton className="h-28" />
      <Skeleton className="h-20" />
    </div>
  );
  if (error) return (
    <div className="flex flex-col items-center justify-center h-full gap-3 p-6">
      <AlertTriangle size={32} className="text-red-400" />
      <p className="text-sm text-red-600 text-center">{error}</p>
      <button onClick={load} className="text-xs text-blue-600 underline">Retry</button>
    </div>
  );
  if (!detail) return null;

  const liveUrl = `/live?device=${encodeURIComponent(detail.device_id)}`;

  return (
    <>
      {/* ── Scrollable body ─────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-5" style={{ scrollbarWidth: 'thin' }}>

        {/* 1. Device ───────────────────────────────────────── */}
        <section>
          <p className="section-label">Device</p>
          <div className="info-card">
            <p className="text-sm font-bold text-navy">{detail.device_id}</p>
            {detail.name     && <p className="text-xs text-muted mt-0.5">{detail.name}</p>}
            {detail.location && <p className="text-xs text-muted">{detail.location}</p>}
          </div>
        </section>

        {/* 2. Reading vs limits ────────────────────────────── */}
        <section>
          <p className="section-label">Reading vs limits</p>
          <div className="info-card flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted">Alert type</span>
              <span className="text-xs font-semibold text-navy">
                {(detail.alert_type || '').replace(/_/g, ' ')}
              </span>
            </div>
            {detail.reading != null && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted">Reading</span>
                <span className="text-sm font-bold" style={{ color: '#EF4444' }}>
                  {detail.reading} {detail.unit || ''}
                </span>
              </div>
            )}
            {detail.worst_status && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted">Worst status</span>
                <span className="text-xs font-semibold text-navy">{detail.worst_status}</span>
              </div>
            )}
          </div>
        </section>

        {/* 3. Timeline ────────────────────────────────────── */}
        <section>
          <p className="section-label">Timeline</p>
          <div className="info-card flex flex-col gap-2">
            <Row label="Opened"   value={fmtDateTime(detail.started_at)} />
            <Row label="Duration" value={elapsedFrom(safeDate(detail.started_at))} />
            {detail.acknowledged_at && <>
              <div className="border-t border-slate-100 my-1" />
              <Row label="Acknowledged" value={fmtDateTime(detail.acknowledged_at)} />
              {detail.acknowledged_by && <Row label="By" value={detail.acknowledged_by} />}
              {detail.acknowledge_note && (
                <div className="mt-1 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  <span className="font-semibold">Note: </span>{detail.acknowledge_note}
                </div>
              )}
            </>}
            {(detail.resolved_at || detail.cleared_at) && <>
              <div className="border-t border-slate-100 my-1" />
              <Row label={detail.cleared_at ? 'Cleared' : 'Resolved'}
                   value={fmtDateTime(detail.resolved_at || detail.cleared_at)} />
              {detail.resolved_by && <Row label="By" value={detail.resolved_by} />}
              {detail.resolution_note && (
                <div className="mt-1 rounded-xl bg-green-50 px-3 py-2 text-xs text-green-800">
                  <span className="font-semibold">Note: </span>{detail.resolution_note}
                </div>
              )}
            </>}
          </div>
        </section>

        {/* 4. Why it was raised ───────────────────────────── */}
        <section>
          <p className="section-label">Why it was raised</p>
          {detail.confidence_pct != null && detail.confidence_pct <= 50 && (
            <div className="flex items-start gap-2 mb-2 px-3 py-2.5 rounded-xl bg-amber-50 border border-amber-200">
              <AlertTriangle size={13} className="text-amber-500 mt-0.5 shrink-0" />
              <p className="text-xs text-amber-700 font-medium">
                Low confidence ({detail.confidence_pct}%) — check the panel directly before acting.
              </p>
            </div>
          )}
          {reasons.length > 0 ? (
            <ul className="flex flex-col gap-1.5">
              {reasons.map((r, i) => (
                <li key={i}
                  className="text-xs text-navy bg-slate-50 px-3 py-2 rounded-xl leading-relaxed"
                  style={{ borderLeft: '3px solid #2F80ED' }}>
                  {r}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted italic">No reasons provided by the tablet.</p>
          )}
        </section>

        {/* 5. Previous readings ───────────────────────────── */}
        <section>
          <p className="section-label">Readings before the alert</p>
          <PreReadingsTable readings={detail.pre_readings} />
        </section>
      </div>

      {/* ── Sticky footer ───────────────────────────────────── */}
      <div className="shrink-0 border-t border-slate-100 p-4 flex flex-col gap-2 bg-white">
        {canAct && status === 'active' && (
          <button onClick={() => setModal('acknowledge')}
            className="w-full py-2.5 rounded-xl text-sm font-semibold transition-colors"
            style={{ background: '#FFFBEB', color: '#92400E' }}>
            Acknowledge…
          </button>
        )}
        {canAct && (status === 'active' || status === 'acknowledged') && (
          <button onClick={() => setModal('resolve')}
            className="w-full py-2.5 rounded-xl text-sm font-semibold transition-colors"
            style={{ background: '#F0FDF4', color: '#14532D' }}>
            Resolve…
          </button>
        )}
        <Link to={liveUrl} onClick={onClose}
          className="w-full py-2.5 rounded-xl text-sm font-semibold text-center flex items-center justify-center gap-2 transition-colors"
          style={{ background: '#EFF6FF', color: '#1D4ED8' }}>
          <ExternalLink size={13} /> View in Live Monitoring
        </Link>
        {canAct && detail.incident_id ? (
          <Link to={`/incidents?id=${detail.incident_id}`} onClick={onClose}
            className="w-full py-2.5 rounded-xl text-sm font-semibold text-center flex items-center justify-center gap-2 transition-colors"
            style={{ background: '#F0FDF4', color: '#14532D' }}>
            <FileText size={13} /> View incident #{detail.incident_id}
          </Link>
        ) : canAct ? (
          <Link to={`/incidents?new=1&alert=${alertId}`} onClick={onClose}
            className="w-full py-2.5 rounded-xl text-sm font-semibold text-center flex items-center justify-center gap-2 transition-colors"
            style={{ background: '#FEF2F2', color: '#991B1B' }}>
            <FileText size={13} /> Create incident…
          </Link>
        ) : null}
        {canAct && (status === 'active' || status === 'acknowledged') && (
          <p className="flex items-center gap-1.5 text-[11px] text-muted justify-center pt-0.5">
            <Info size={11} /> Acknowledging does not change the device status.
          </p>
        )}
      </div>

      {/* Note modal */}
      {modal && (
        <NoteModal
          title={modal === 'acknowledge' ? 'Acknowledge Alert' : 'Resolve Alert'}
          hint={
            modal === 'acknowledge'
              ? 'Describe what you have observed or done.'
              : 'Describe how the issue was resolved.'
          }
          isAck={modal === 'acknowledge'}
          loading={acting}
          onConfirm={(note) => handleAction(modal, note)}
          onCancel={() => setModal(null)}
        />
      )}
    </>
  );
}

/** Tiny label-value row used in timeline / reading sections */
function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-xs text-muted shrink-0">{label}</span>
      <span className="text-xs font-semibold text-navy text-right">{value}</span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Full-height side-panel drawer
// ─────────────────────────────────────────────────────────────────────────────
function AlertDrawerPanel({ alertId, drawerKey, canAct, onClose, onActionDone }) {
  // Close on Escape
  useEffect(() => {
    if (!alertId) return;
    const h = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [alertId, onClose]);

  if (!alertId) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true"
      aria-label={`Alert #${alertId} detail`}>
      {/* Dimmed overlay */}
      <div className="absolute inset-0 bg-navy/25 backdrop-blur-[2px]"
        onClick={onClose} aria-hidden="true" />

      {/* Panel */}
      <div className="drawer-in relative z-10 w-full sm:w-[480px] max-w-full h-full bg-white shadow-2xl flex flex-col">
        {/* Sticky header */}
        <div className="shrink-0 flex items-center justify-between gap-3 px-5 py-4 border-b border-slate-100 bg-white">
          <div className="flex items-center gap-2 flex-wrap min-w-0">
            <span className="text-sm font-bold text-navy">Alert #{alertId}</span>
          </div>
          <button onClick={onClose} aria-label="Close"
            className="shrink-0 p-1.5 rounded-lg text-muted hover:bg-slate-100 hover:text-navy transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Body + footer rendered by AlertDetailPanel */}
        <AlertDetailPanel
          key={`${alertId}-${drawerKey}`}
          alertId={alertId}
          canAct={canAct}
          onClose={onClose}
          onActionDone={onActionDone}
        />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Duration cell — ticks every second for active alerts
// ─────────────────────────────────────────────────────────────────────────────
function DurationCell({ alert }) {
  const status   = deriveStatus(alert);
  const isActive = status === 'active';

  const sinceOpen = useLiveDuration(alert.started_at,          isActive);
  const sinceAck  = useLiveDuration(alert.acknowledged_at,     false);
  const sinceRes  = useLiveDuration(alert.resolved_at || alert.cleared_at, false);

  if (status === 'active')
    return <span className="font-medium" style={{ color: '#EF4444' }}>unack'd {sinceOpen}</span>;
  if (status === 'acknowledged')
    return <span>ack'd {sinceAck} ago</span>;
  return <span>resolved {sinceRes} ago</span>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Table row
// ─────────────────────────────────────────────────────────────────────────────
function AlertTableRow({ alert, onSelect, canAct, onQuickAck, onQuickResolve }) {
  const status   = deriveStatus(alert);
  const reading  = alertReading(alert);
  const liveUrl  = `/live?device=${encodeURIComponent(alert.device_id)}`;

  return (
    <tr
      className="hover:bg-blue-50/50 cursor-pointer transition-colors group"
      onClick={() => onSelect(alert.id)}
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onSelect(alert.id)}
      aria-label={`Alert ${alert.id}: ${alert.device_id}`}
    >
      {/* Severity stripe */}
      <td className="pl-3 pr-2 py-3 w-1.5">
        <div className="w-1 min-h-[32px] rounded-full h-full"
          style={{ background: severityBorderColor(alert.severity) }} />
      </td>

      {/* ID */}
      <td className="py-3 pr-3 text-xs font-mono font-semibold text-muted whitespace-nowrap">
        #{alert.id}
      </td>

      {/* Device — link to Live Monitoring */}
      <td className="py-3 pr-3">
        <Link
          to={liveUrl}
          onClick={e => e.stopPropagation()}
          className="text-xs font-bold text-primary hover:underline"
          title="Open in Live Monitoring"
        >
          {alert.device_id}
        </Link>
      </td>

      {/* Type */}
      <td className="py-3 pr-3">
        <span className="text-xs text-muted">
          {(alert.alert_type || '').replace(/_/g, ' ')}
        </span>
      </td>

      {/* Severity */}
      <td className="py-3 pr-3">
        <SeverityBadge severity={alert.severity} />
      </td>

      {/* Reading — numeric value + unit */}
      <td className="py-3 pr-3 text-xs font-semibold text-navy whitespace-nowrap">
        {reading}
      </td>

      {/* Opened */}
      <td className="py-3 pr-3 text-xs text-muted whitespace-nowrap">
        {fmtDateTime(alert.started_at)}
      </td>

      {/* Duration — live-ticking for active */}
      <td className="py-3 pr-3 text-xs text-muted whitespace-nowrap">
        <DurationCell alert={alert} />
      </td>

      {/* Status */}
      <td className="py-3 pr-3">
        <StatusBadge status={status} />
      </td>

      {/* Actions column — always visible */}
      <td className="py-3 pr-3">
        <div className="flex items-center gap-1.5">
          {/* View button */}
          <button
            onClick={e => { e.stopPropagation(); onSelect(alert.id); }}
            className="flex items-center gap-1 text-[10px] font-bold px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors whitespace-nowrap"
          >
            View <ChevronRight size={10} />
          </button>

          {/* Live icon button */}
          <Link
            to={liveUrl}
            onClick={e => e.stopPropagation()}
            title="Open in Live Monitoring"
            aria-label="Open in Live Monitoring"
            className="p-1.5 rounded-lg text-muted hover:bg-slate-100 hover:text-primary transition-colors"
          >
            <Monitor size={13} />
          </Link>

          {/* Quick Ack (canAct only, active only) */}
          {canAct && status === 'active' && (
            <button
              onClick={e => { e.stopPropagation(); onQuickAck(alert.id); }}
              title="Acknowledge"
              className="text-[10px] font-bold px-2 py-1 rounded-lg bg-amber-50 text-amber-700 hover:bg-amber-100 transition-colors opacity-0 group-hover:opacity-100"
            >
              Ack
            </button>
          )}

          {/* Quick Resolve (canAct only, active/ack) */}
          {canAct && (status === 'active' || status === 'acknowledged') && (
            <button
              onClick={e => { e.stopPropagation(); onQuickResolve(alert.id); }}
              title="Resolve"
              className="text-[10px] font-bold px-2 py-1 rounded-lg bg-green-50 text-green-700 hover:bg-green-100 transition-colors opacity-0 group-hover:opacity-100"
            >
              Resolve
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Empty state
// ─────────────────────────────────────────────────────────────────────────────
function EmptyState({ tab }) {
  return (
    <tr>
      <td colSpan={11} className="py-20 text-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-14 h-14 rounded-2xl bg-green-50 flex items-center justify-center">
            <CheckCircle size={24} className="text-green-500" />
          </div>
          <p className="text-sm font-semibold text-navy">No {tab} alerts</p>
          <p className="text-xs text-muted">
            {tab === 'active'
              ? 'All devices are operating within safe thresholds.'
              : `No ${tab} alerts yet.`}
          </p>
        </div>
      </td>
    </tr>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tabs config
// ─────────────────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'active',       label: 'Active'       },
  { id: 'acknowledged', label: 'Acknowledged' },
  { id: 'resolved',     label: 'Resolved'     },
  { id: 'all',          label: 'All'          },
];

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────
export default function PortalAlerts({ alerts: activeProp = [], onAcknowledge, onResolve }) {
  const { role } = useAuth();
  const canAct   = role !== 'VIEWER';

  const [searchParams, setSearchParams] = useSearchParams();
  const [allAlerts,    setAllAlerts]    = useState(null);
  const [loadingAll,   setLoadingAll]   = useState(false);

  const [selectedId,  setSelectedId]  = useState(null);
  const [drawerKey,   setDrawerKey]   = useState(0);

  const [quickModal,  setQuickModal]  = useState(null);
  const [quickActing, setQuickActing] = useState(false);

  const rawParam = searchParams.get('status') || 'active';
  const tab      = VALID_TABS.includes(rawParam) ? rawParam : 'active';

  const loadAll = useCallback(() => {
    setLoadingAll(true);
    getAlerts('all')
      .then(d => setAllAlerts(d || []))
      .catch(() => setAllAlerts([]))
      .finally(() => setLoadingAll(false));
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadAll(); }, [activeProp]);

  function handleTabChange(id) {
    setSearchParams({ status: id }, { replace: false });
  }

  const pool = tab === 'active'
    ? activeProp
    : (allAlerts || []).filter(a => tab === 'all' || deriveStatus(a) === tab);

  const counts = allAlerts === null ? null : {
    active:       allAlerts.filter(a => deriveStatus(a) === 'active').length,
    acknowledged: allAlerts.filter(a => deriveStatus(a) === 'acknowledged').length,
    resolved:     allAlerts.filter(a => deriveStatus(a) === 'resolved').length,
    all:          allAlerts.length,
  };

  function handleDrawerActionDone(type, errMsg) {
    setDrawerKey(k => k + 1);
    if (!errMsg) {
      if (type === 'acknowledge') onAcknowledge?.(selectedId, '');
      else                        onResolve?.(selectedId, '');
    }
    loadAll();
  }

  async function handleQuickAction(note) {
    if (!quickModal) return;
    setQuickActing(true);
    try {
      if (quickModal.type === 'acknowledge') await onAcknowledge(quickModal.alertId, note);
      else                                   await onResolve(quickModal.alertId, note);
    } finally {
      setQuickActing(false);
      setQuickModal(null);
      loadAll();
    }
  }

  return (
    <>
      {/* Inline styles for repeated micro-patterns */}
      <style>{`
        .section-label {
          font-size: 10px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: #8A94A6;
          margin-bottom: 6px;
        }
        .info-card {
          background: #F8FAFF;
          border-radius: 12px;
          padding: 12px 14px;
        }
      `}</style>

      <div className="p-5 flex flex-col gap-5 page-fade-in">
        {/* Title */}
        <div>
          <h1 className="text-lg font-bold text-navy">Alerts</h1>
          <p className="text-xs text-muted mt-0.5">
            Priority order: critical first, oldest unacknowledged first
          </p>
          <p className="text-[11px] mt-0.5" style={{ color: '#A0AEC0' }}>
            Click an alert to see details
          </p>
        </div>

        {/* Tabs */}
        <div
          className="flex flex-wrap gap-1 p-1.5 rounded-2xl w-fit"
          style={{ background: '#fff', boxShadow: '0 4px 24px rgba(80,110,180,0.08)' }}
          role="tablist"
        >
          {TABS.map(({ id, label }) => {
            const isActive = tab === id;
            const count    = counts?.[id];
            return (
              <button key={id} role="tab" aria-selected={isActive}
                onClick={() => handleTabChange(id)}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-1"
                style={{
                  background: isActive ? '#2F80ED' : 'transparent',
                  color:      isActive ? '#fff'    : '#8A94A6',
                }}>
                {label}
                {count != null && (
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-none"
                    style={{
                      background: isActive ? 'rgba(255,255,255,0.25)' : '#F0F4FF',
                      color:      isActive ? '#fff'                   : '#8A94A6',
                    }}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Table */}
        <div className="bg-white rounded-2xl overflow-hidden" style={CARD}>
          {loadingAll ? (
            <div className="flex flex-col gap-3 p-5">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-14" />)}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="pl-3 pr-2 py-3 w-1.5" aria-hidden="true" />
                    {['ID','Device','Type','Severity','Reading','Opened','Duration','Status','Actions'].map(h => (
                      <th key={h}
                        className="py-3 pr-3 text-[10px] font-bold uppercase tracking-widest text-muted whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {pool.length === 0
                    ? <EmptyState tab={tab} />
                    : pool.map(a => (
                      <AlertTableRow
                        key={a.id}
                        alert={a}
                        canAct={canAct}
                        onSelect={setSelectedId}
                        onQuickAck={id  => setQuickModal({ type: 'acknowledge', alertId: id })}
                        onQuickResolve={id => setQuickModal({ type: 'resolve',     alertId: id })}
                      />
                    ))
                  }
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Detail panel */}
      <AlertDrawerPanel
        alertId={selectedId}
        drawerKey={drawerKey}
        canAct={canAct}
        onClose={() => setSelectedId(null)}
        onActionDone={handleDrawerActionDone}
      />

      {/* Quick-action modal */}
      {quickModal && (
        <NoteModal
          title={quickModal.type === 'acknowledge' ? 'Acknowledge Alert' : 'Resolve Alert'}
          hint={
            quickModal.type === 'acknowledge'
              ? 'Describe what you have observed or done.'
              : 'Describe how the issue was resolved.'
          }
          isAck={quickModal.type === 'acknowledge'}
          loading={quickActing}
          onConfirm={handleQuickAction}
          onCancel={() => setQuickModal(null)}
        />
      )}
    </>
  );
}
