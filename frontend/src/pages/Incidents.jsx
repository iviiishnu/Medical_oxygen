/**
 * pages/Incidents.jsx
 * ===================
 * Incident Management page — per lead spec.
 *
 * Layout mirrors the Alerts page:
 *   • Tabs (Open / In Progress / Closed / All) with count pills, URL-synced
 *   • Priority table with visible View button per row
 *   • Full-height side-panel drawer (sticky header + scrollable body + sticky footer)
 *   • Create Incident modal (prefill from ?new=1&alert=<id>)
 *   • Viewer role: read-only (no create, no status change, no notes)
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import {
  FileText, Plus, X, ChevronRight, Info,
  CheckCircle, Clock, AlertTriangle, Archive,
} from 'lucide-react';
import {
  getIncidents, getIncident, createIncident,
  patchIncident, addIncidentNote,
  getAlerts,
} from '../api/portal';
import { useAuth }   from '../hooks/useAuth';
import { Skeleton }  from '../components/ui/Skeleton';

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────
const VALID_TABS   = ['open', 'in_progress', 'closed', 'all'];
const CARD         = { boxShadow: '0 4px 24px rgba(80,110,180,0.08)' };
const TABS_CONFIG  = [
  { id: 'open',        label: 'Open'        },
  { id: 'in_progress', label: 'In Progress' },
  { id: 'closed',      label: 'Closed'      },
  { id: 'all',         label: 'All'         },
];

const STATUS_STYLES = {
  open:        { bg: '#FEF2F2', color: '#DC2626' },
  in_progress: { bg: '#FFFBEB', color: '#D97706' },
  closed:      { bg: '#F0FDF4', color: '#16A34A' },
};

const SEVERITY_STYLES = {
  Critical: { bg: '#FEF2F2', color: '#EF4444' },
  Warning:  { bg: '#FFFBEB', color: '#D97706' },
};

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
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

function timeAgo(raw) {
  const d = safeDate(raw);
  if (!d) return '—';
  const diff = Date.now() - d.getTime();
  if (diff < 0) return 'just now';
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m ago`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Badge components
// ─────────────────────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const cfg = STATUS_STYLES[status] || { bg: '#F4F7FC', color: '#6B7280' };
  const label = (status || '').replace('_', ' ');
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold capitalize"
      style={{ background: cfg.bg, color: cfg.color }}>
      {label}
    </span>
  );
}

function SeverityBadge({ severity }) {
  if (!severity) return null;
  const cfg = SEVERITY_STYLES[severity] || { bg: '#F4F7FC', color: '#6B7280' };
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold"
      style={{ background: cfg.bg, color: cfg.color }}>
      {severity}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Create incident modal
// ─────────────────────────────────────────────────────────────────────────────
function CreateModal({ prefillAlertId, onClose, onCreated }) {
  const { user } = useAuth();
  const [form, setForm] = useState({
    title:          '',
    device_id:      '',
    alert_id:       prefillAlertId ? String(prefillAlertId) : '',
    description:    '',
    possible_cause: '',
    severity:       'Warning',
    assigned_to:    '',
  });
  const [saving, setSaving] = useState(false);
  const [error,  setError]  = useState('');
  const titleRef = useRef(null);

  useEffect(() => { titleRef.current?.focus(); }, []);
  useEffect(() => {
    const h = e => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);

  function set(k, v) { setForm(f => ({ ...f, [k]: v })); }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.title.trim()) { setError('Title is required'); return; }
    setSaving(true);
    setError('');
    try {
      const payload = {
        title:          form.title.trim(),
        device_id:      form.device_id.trim() || null,
        alert_id:       form.alert_id ? parseInt(form.alert_id, 10) : null,
        description:    form.description.trim()    || null,
        possible_cause: form.possible_cause.trim() || null,
        severity:       form.severity,
        assigned_to:    form.assigned_to.trim()    || null,
      };
      const created = await createIncident(payload);
      onCreated(created);
    } catch (e) {
      setError(e.message || 'Failed to create incident');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />
      <div className="relative bg-white rounded-2xl w-full max-w-lg flex flex-col max-h-[90vh]"
        style={{ boxShadow: '0 20px 60px rgba(0,0,0,0.20)' }}>

        {/* Modal header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 shrink-0">
          <h3 className="text-sm font-bold text-navy">Create Incident</h3>
          <button onClick={onClose} className="p-1 rounded-lg text-muted hover:bg-slate-100 hover:text-navy">
            <X size={16} />
          </button>
        </div>

        {/* Modal body */}
        <form id="create-incident-form" onSubmit={handleSubmit}
          className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-4" style={{ scrollbarWidth: 'thin' }}>
          {error && (
            <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
              <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {error}
            </div>
          )}

          <Field label="Title *">
            <input ref={titleRef} value={form.title} onChange={e => set('title', e.target.value)}
              placeholder="Short description of the incident" required
              className="inp" />
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field label="Device ID">
              <input value={form.device_id} onChange={e => set('device_id', e.target.value)}
                placeholder="e.g. tab-01" className="inp" />
            </Field>
            <Field label="Related Alert ID">
              <input value={form.alert_id} onChange={e => set('alert_id', e.target.value)}
                placeholder="numeric ID" type="number" min="1" className="inp" />
            </Field>
          </div>

          <Field label="Description">
            <textarea value={form.description} onChange={e => set('description', e.target.value)}
              rows={3} placeholder="What happened?" className="inp resize-none" />
          </Field>

          <Field label="Possible Cause">
            <textarea value={form.possible_cause} onChange={e => set('possible_cause', e.target.value)}
              rows={2} placeholder="Root cause hypothesis…" className="inp resize-none" />
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field label="Severity">
              <select value={form.severity} onChange={e => set('severity', e.target.value)} className="inp">
                <option>Warning</option>
                <option>Critical</option>
              </select>
            </Field>
            <Field label="Assigned to">
              <input value={form.assigned_to} onChange={e => set('assigned_to', e.target.value)}
                placeholder="Username or name" className="inp" />
            </Field>
          </div>
        </form>

        {/* Modal footer */}
        <div className="flex justify-end gap-2 px-6 py-4 border-t border-slate-100 shrink-0">
          <button type="button" onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-muted hover:bg-slate-100 transition-colors">
            Cancel
          </button>
          <button type="submit" form="create-incident-form" disabled={saving}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-white disabled:opacity-60"
            style={{ background: '#2F80ED' }}>
            {saving ? 'Creating…' : 'Create incident'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-semibold text-navy">{label}</label>
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Incident detail drawer
// ─────────────────────────────────────────────────────────────────────────────
function IncidentDrawer({ incidentId, canWrite, onClose, onUpdated }) {
  const [detail,   setDetail]   = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(null);
  const [noteText, setNoteText] = useState('');
  const [addingNote, setAddingNote] = useState(false);

  // Status update state
  const [patchStatus,     setPatchStatus]     = useState('');
  const [resolution,      setResolution]      = useState('');
  const [savingStatus,    setSavingStatus]    = useState(false);
  const [statusError,     setStatusError]     = useState('');

  const load = useCallback(async () => {
    if (!incidentId) return;
    setLoading(true);
    setError(null);
    try {
      const d = await getIncident(incidentId);
      setDetail(d);
      setPatchStatus(d.status);
      setResolution(d.resolution || '');
    } catch (e) {
      setError(e.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [incidentId]);

  useEffect(() => { load(); }, [load]);

  // Esc to close
  useEffect(() => {
    if (!incidentId) return;
    const h = e => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [incidentId, onClose]);

  async function handleStatusSave() {
    if (patchStatus === 'closed' && !resolution.trim()) {
      setStatusError('A resolution is required to close an incident');
      return;
    }
    setSavingStatus(true);
    setStatusError('');
    try {
      await patchIncident(incidentId, {
        status:     patchStatus,
        resolution: resolution.trim() || null,
      });
      await load();
      onUpdated();
    } catch (e) {
      setStatusError(e.message || 'Update failed');
    } finally {
      setSavingStatus(false);
    }
  }

  async function handleAddNote() {
    if (!noteText.trim()) return;
    setAddingNote(true);
    try {
      await addIncidentNote(incidentId, noteText.trim());
      setNoteText('');
      await load();
    } catch {}
    finally { setAddingNote(false); }
  }

  if (!incidentId) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true"
      aria-label={`Incident #${incidentId}`}>
      <div className="absolute inset-0 bg-navy/25 backdrop-blur-[2px]"
        onClick={onClose} aria-hidden="true" />

      <div className="drawer-in relative z-10 w-full sm:w-[480px] max-w-full h-full bg-white shadow-2xl flex flex-col">
        {/* Sticky header */}
        <div className="shrink-0 flex items-center justify-between gap-3 px-5 py-4 border-b border-slate-100 bg-white">
          <div className="flex items-center gap-2 flex-wrap min-w-0">
            <span className="text-sm font-bold text-navy truncate">
              {loading ? `Incident #${incidentId}` : (detail?.title || `Incident #${incidentId}`)}
            </span>
            {detail && <SeverityBadge severity={detail.severity} />}
            {detail && <StatusBadge status={detail.status} />}
          </div>
          <button onClick={onClose} aria-label="Close"
            className="shrink-0 p-1.5 rounded-lg text-muted hover:bg-slate-100 hover:text-navy">
            <X size={18} />
          </button>
        </div>

        {/* Scrollable body */}
        {loading ? (
          <div className="flex-1 p-6 flex flex-col gap-4">
            <Skeleton className="h-20" />
            <Skeleton className="h-14" />
            <Skeleton className="h-28" />
          </div>
        ) : error ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 p-6">
            <AlertTriangle size={28} className="text-red-400" />
            <p className="text-sm text-red-600">{error}</p>
            <button onClick={load} className="text-xs text-blue-600 underline">Retry</button>
          </div>
        ) : detail ? (
          <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-5" style={{ scrollbarWidth: 'thin' }}>

            {/* Incident info */}
            <section>
              <SectionLabel>Incident</SectionLabel>
              <div className="info-card flex flex-col gap-2">
                <Row label="ID"         value={`#${detail.id}`} />
                <Row label="Device"     value={detail.device_id || '—'} />
                <Row label="Created by" value={detail.created_by} />
                <Row label="Created"    value={fmtDateTime(detail.created_at)} />
                {detail.assigned_to && <Row label="Assigned to" value={detail.assigned_to} />}
                {detail.closed_at   && <Row label="Closed"      value={fmtDateTime(detail.closed_at)} />}
              </div>
            </section>

            {detail.description && (
              <section>
                <SectionLabel>Description</SectionLabel>
                <div className="info-card text-xs text-navy leading-relaxed">{detail.description}</div>
              </section>
            )}

            {detail.possible_cause && (
              <section>
                <SectionLabel>Possible Cause</SectionLabel>
                <div className="info-card text-xs text-navy leading-relaxed">{detail.possible_cause}</div>
              </section>
            )}

            {detail.resolution && (
              <section>
                <SectionLabel>Resolution</SectionLabel>
                <div className="info-card text-xs text-navy leading-relaxed">{detail.resolution}</div>
              </section>
            )}

            {/* Linked alert */}
            {detail.linked_alert && (
              <section>
                <SectionLabel>Linked Alert #{detail.alert_id}</SectionLabel>
                <div className="info-card flex flex-col gap-2">
                  <Row label="Device"    value={detail.linked_alert.device_id} />
                  <Row label="Type"      value={(detail.linked_alert.alert_type || '').replace(/_/g, ' ')} />
                  {detail.linked_alert.severity && <Row label="Severity" value={detail.linked_alert.severity} />}
                  {detail.linked_alert.reading != null && (
                    <Row label="Reading" value={`${detail.linked_alert.reading} ${detail.linked_alert.unit || ''}`} />
                  )}
                  {(detail.linked_alert.reasons || []).length > 0 && (
                    <div className="mt-1">
                      <p className="text-[10px] font-bold uppercase tracking-widest text-muted mb-1">Reasons</p>
                      <ul className="flex flex-col gap-1">
                        {detail.linked_alert.reasons.map((r, i) => (
                          <li key={i} className="text-[11px] text-navy bg-white border border-slate-100 px-3 py-1.5 rounded-xl">{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <Link to={`/alerts?status=all`}
                    className="text-[11px] font-semibold text-primary hover:underline flex items-center gap-1 mt-1">
                    View in Alerts <ChevronRight size={11} />
                  </Link>
                </div>
              </section>
            )}

            {/* Notes */}
            <section>
              <SectionLabel>Notes ({(detail.notes || []).length})</SectionLabel>
              {(detail.notes || []).length === 0 ? (
                <p className="text-xs text-muted italic">No notes yet.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {detail.notes.map(n => (
                    <li key={n.id} className="bg-slate-50 rounded-xl px-3 py-2.5">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[11px] font-semibold text-navy">{n.author}</span>
                        <span className="text-[10px] text-muted">{timeAgo(n.created_at)}</span>
                      </div>
                      <p className="text-xs text-navy leading-relaxed">{n.note}</p>
                    </li>
                  ))}
                </ul>
              )}

              {/* Add note box (write users only) */}
              {canWrite && (
                <div className="mt-3 flex flex-col gap-2">
                  <textarea
                    value={noteText}
                    onChange={e => setNoteText(e.target.value)}
                    rows={2}
                    placeholder="Add a note…"
                    className="w-full px-3 py-2 text-sm rounded-xl border border-slate-200 bg-slate-50 outline-none focus:border-blue-400 resize-none"
                  />
                  <button onClick={handleAddNote} disabled={addingNote || !noteText.trim()}
                    className="self-end px-4 py-2 rounded-xl text-xs font-semibold text-white disabled:opacity-50"
                    style={{ background: '#2F80ED' }}>
                    {addingNote ? 'Adding…' : 'Add note'}
                  </button>
                </div>
              )}
            </section>

          </div>
        ) : null}

        {/* Sticky footer — status update + close button (write users only) */}
        {detail && canWrite && (
          <div className="shrink-0 border-t border-slate-100 px-5 py-4 flex flex-col gap-3 bg-white">
            {statusError && (
              <p className="text-[11px] text-red-600 flex items-center gap-1.5">
                <Info size={11} /> {statusError}
              </p>
            )}
            <div className="flex items-center gap-2">
              <select
                value={patchStatus}
                onChange={e => { setPatchStatus(e.target.value); setStatusError(''); }}
                className="flex-1 text-xs rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 outline-none focus:border-blue-400"
              >
                <option value="open">Open</option>
                <option value="in_progress">In Progress</option>
                <option value="closed">Closed</option>
              </select>
              <button onClick={handleStatusSave} disabled={savingStatus}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-white disabled:opacity-60"
                style={{ background: '#2F80ED' }}>
                {savingStatus ? 'Saving…' : 'Update'}
              </button>
            </div>
            {patchStatus === 'closed' && (
              <textarea
                value={resolution}
                onChange={e => setResolution(e.target.value)}
                rows={2}
                placeholder="Resolution (required to close)…"
                className="w-full px-3 py-2 text-sm rounded-xl border border-slate-200 bg-slate-50 outline-none focus:border-blue-400 resize-none"
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <p className="text-[10px] font-bold uppercase tracking-widest text-muted mb-1.5">{children}</p>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-xs text-muted shrink-0">{label}</span>
      <span className="text-xs font-semibold text-navy text-right">{value ?? '—'}</span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Table row
// ─────────────────────────────────────────────────────────────────────────────
function IncidentRow({ incident, onSelect }) {
  return (
    <tr className="hover:bg-blue-50/50 cursor-pointer transition-colors group"
      onClick={() => onSelect(incident.id)}
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onSelect(incident.id)}>
      {/* Status stripe */}
      <td className="pl-3 pr-2 py-3 w-1.5">
        <div className="w-1 min-h-[32px] rounded-full"
          style={{ background: STATUS_STYLES[incident.status]?.color || '#94A3B8' }} />
      </td>
      <td className="py-3 pr-3 text-xs font-mono font-semibold text-muted">#{incident.id}</td>
      <td className="py-3 pr-3 text-xs font-semibold text-navy">{incident.device_id || '—'}</td>
      <td className="py-3 pr-3">
        {incident.alert_id
          ? <span className="text-xs text-primary font-semibold">#{incident.alert_id}</span>
          : <span className="text-xs text-muted">—</span>
        }
      </td>
      <td className="py-3 pr-3 max-w-[220px]">
        <p className="text-xs font-semibold text-navy truncate">{incident.title}</p>
      </td>
      <td className="py-3 pr-3 text-xs text-muted whitespace-nowrap">{timeAgo(incident.created_at)}</td>
      <td className="py-3 pr-3 text-xs text-muted">{incident.assigned_to || '—'}</td>
      <td className="py-3 pr-3">
        <StatusBadge status={incident.status} />
      </td>
      <td className="py-3 pr-3">
        <button
          onClick={e => { e.stopPropagation(); onSelect(incident.id); }}
          className="flex items-center gap-1 text-[10px] font-bold px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors whitespace-nowrap">
          View <ChevronRight size={10} />
        </button>
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
      <td colSpan={9} className="py-20 text-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-14 h-14 rounded-2xl bg-green-50 flex items-center justify-center">
            <CheckCircle size={24} className="text-green-500" />
          </div>
          <p className="text-sm font-semibold text-navy">No {tab.replace('_', ' ')} incidents</p>
        </div>
      </td>
    </tr>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────
export default function Incidents() {
  const { role } = useAuth();
  const canWrite = role !== 'VIEWER';

  const [searchParams, setSearchParams] = useSearchParams();
  const [allIncidents, setAllIncidents] = useState(null);
  const [loading,      setLoading]      = useState(false);
  const [selectedId,   setSelectedId]   = useState(null);
  const [showCreate,   setShowCreate]   = useState(false);

  // Prefill from ?new=1&alert=<id>
  const prefillAlertId = searchParams.get('alert')
    ? parseInt(searchParams.get('alert'), 10)
    : null;

  useEffect(() => {
    if (searchParams.get('new') === '1') {
      setShowCreate(true);
    }
    // ?id=<n> deep-links directly to the incident drawer
    const idParam = searchParams.get('id');
    if (idParam) {
      const n = parseInt(idParam, 10);
      if (!isNaN(n)) setSelectedId(n);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const rawParam = searchParams.get('status') || 'open';
  const tab = VALID_TABS.includes(rawParam) ? rawParam : 'open';

  const loadAll = useCallback(() => {
    setLoading(true);
    getIncidents('all')
      .then(d => setAllIncidents(d || []))
      .catch(() => setAllIncidents([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  function handleTabChange(id) {
    setSearchParams({ status: id }, { replace: false });
  }

  const pool = (allIncidents || []).filter(i => tab === 'all' || i.status === tab);

  const counts = allIncidents === null ? null : {
    open:        allIncidents.filter(i => i.status === 'open').length,
    in_progress: allIncidents.filter(i => i.status === 'in_progress').length,
    closed:      allIncidents.filter(i => i.status === 'closed').length,
    all:         allIncidents.length,
  };

  function handleCreated(inc) {
    setShowCreate(false);
    loadAll();
    setSelectedId(inc.id);
    // Strip ?new and ?alert from URL
    setSearchParams({ status: tab }, { replace: true });
  }

  return (
    <>
      {/* Shared micro-styles */}
      <style>{`
        .inp {
          width: 100%;
          padding: 8px 12px;
          font-size: 13px;
          border-radius: 12px;
          border: 1px solid #E2E8F0;
          background: #F8FAFF;
          outline: none;
        }
        .inp:focus { border-color: #60A5FA; }
        .info-card {
          background: #F8FAFF;
          border-radius: 12px;
          padding: 12px 14px;
        }
      `}</style>

      <div className="p-5 flex flex-col gap-5 page-fade-in">
        {/* Title */}
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-lg font-bold text-navy">Incident Management</h1>
            <p className="text-xs text-muted mt-0.5">Track, document and review incidents</p>
          </div>
          {canWrite && (
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white transition-colors"
              style={{ background: '#2F80ED' }}>
              <Plus size={14} /> Create incident
            </button>
          )}
        </div>

        {/* Tabs */}
        <div className="flex flex-wrap gap-1 p-1.5 rounded-2xl w-fit"
          style={{ background: '#fff', boxShadow: '0 4px 24px rgba(80,110,180,0.08)' }}
          role="tablist">
          {TABS_CONFIG.map(({ id, label }) => {
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
          {loading ? (
            <div className="flex flex-col gap-3 p-5">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-14" />)}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="pl-3 pr-2 py-3 w-1.5" aria-hidden="true" />
                    {['ID','Device','Alert','Title','Reported','Assigned to','Status',''].map(h => (
                      <th key={h} className="py-3 pr-3 text-[10px] font-bold uppercase tracking-widest text-muted whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {pool.length === 0
                    ? <EmptyState tab={tab} />
                    : pool.map(i => (
                      <IncidentRow key={i.id} incident={i} onSelect={setSelectedId} />
                    ))
                  }
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Detail drawer */}
      {selectedId && (
        <IncidentDrawer
          incidentId={selectedId}
          canWrite={canWrite}
          onClose={() => setSelectedId(null)}
          onUpdated={loadAll}
        />
      )}

      {/* Create modal */}
      {showCreate && (
        <CreateModal
          prefillAlertId={prefillAlertId}
          onClose={() => { setShowCreate(false); setSearchParams({ status: tab }, { replace: true }); }}
          onCreated={handleCreated}
        />
      )}
    </>
  );
}
