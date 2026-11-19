/**
 * pages/Analytics.jsx
 * ===================
 * Analytics & Reports page — replaces the old purity-based placeholder.
 *
 * Data comes from GET /api/analytics (Oxygen / Medical Air, kg/cm2 only).
 *   • Date filter: Today / 7d / 30d / Custom — synced to ?range=<id>
 *   • Summary cards, alerts/day stacked by device, type & device breakdowns
 *   • Device performance table (uptime, offline, readings, last message)
 *   • Pressure trend: stepAfter, one line per device, dashed safe limits
 *   • Incident summary card, CSV report downloads (blob + bearer token)
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import {
  Bell, CheckCircle, Clock, FileWarning, FileText, Download,
  CalendarDays, AlertTriangle, Activity, Timer, X, Info,
} from 'lucide-react';
import { getAnalytics, downloadCsv } from '../api/portal';
import { Skeleton } from '../components/ui/Skeleton';

// ── Palette ────────────────────────────────────────────────────────────────
const SERIES_COLORS = ['#2F80ED', '#22C55E', '#F5A524', '#F0386B', '#8B5CF6', '#14B8A6'];
const colorFor = (i) => SERIES_COLORS[i % SERIES_COLORS.length];

const TYPE_STYLES = {
  PANEL_CRITICAL:  { label: 'Panel critical', bg: '#FEF2F2', fg: '#DC2626' },
  TABLET_OFFLINE:  { label: 'Tablet offline', bg: '#FFF7ED', fg: '#EA580C' },
  UNREADABLE:      { label: 'Unreadable',     bg: '#FFFBEB', fg: '#D97706' },
  OTHER:           { label: 'Other',          bg: '#F4F7FC', fg: '#6B7280' },
};

const RANGES = [
  { id: 'today', label: 'Today' },
  { id: '1d',    label: 'Last 24 h' },
  { id: '7d',    label: 'Last 7 days' },
  { id: '30d',   label: 'Last 30 days' },
  { id: 'custom', label: 'Custom' },
];
const DEFAULT_RANGE = '7d';

// ── Helpers ─────────────────────────────────────────────────────────────────

function fmtDuration(seconds) {
  if (seconds == null) return '—';
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

function fmtDateTime(raw) {
  if (!raw) return '—';
  const d = new Date(raw);
  return isNaN(d.getTime())
    ? '—'
    : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function sameLocalDay(a, b) {
  return a.getFullYear() === b.getFullYear()
      && a.getMonth() === b.getMonth()
      && a.getDate() === b.getDate();
}

/** "Nov 19" style short date from a Date or ISO string. */
function fmtShortDate(input) {
  const d = input instanceof Date ? input : new Date(input);
  return isNaN(d.getTime())
    ? '—'
    : d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

/** Date → "YYYY-MM-DD" (local). */
function toISODate(d) {
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

const DAY_MS = 86400e3;

// ── Shared bits ─────────────────────────────────────────────────────────────
function Card({ title, subtitle, icon: Icon, children, className = '' }) {
  return (
    <div className={`bg-white rounded-2xl p-5 flex flex-col gap-4 ${className}`}
      style={{ boxShadow: '0 4px 24px rgba(80,110,180,0.08)' }}>
      {(title || Icon) && (
        <div className="flex items-start justify-between gap-3">
          <div>
            {title && <h3 className="text-sm font-semibold text-navy">{title}</h3>}
            {subtitle && <p className="text-xs mt-0.5 text-muted">{subtitle}</p>}
          </div>
          {Icon && <Icon size={16} className="text-muted shrink-0 mt-0.5" />}
        </div>
      )}
      {children}
    </div>
  );
}

function Tip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl p-3 text-xs"
      style={{ background: '#fff', border: '1px solid #E8EEFA', boxShadow: '0 8px 24px rgba(80,110,180,0.12)', minWidth: 130 }}>
      {label && <p className="mb-2 font-medium text-muted">{label}</p>}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 mb-1">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color || p.fill || '#2F80ED' }} />
          <span className="text-navy">{p.name}</span>
          <span className="ml-auto font-bold text-navy">
            {typeof p.value === 'number' ? (Number.isInteger(p.value) ? p.value : p.value.toFixed(2)) : p.value}
          </span>
        </div>
      ))}
    </div>
  );
}

function Empty({ text = 'No data in this period.' }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-8">
      <span style={{ fontSize: 22 }}>📊</span>
      <p className="text-xs text-center max-w-xs text-muted">{text}</p>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub, tint }) {
  return (
    <div className="bg-white rounded-2xl p-4 flex items-center gap-4"
      style={{ boxShadow: '0 4px 24px rgba(80,110,180,0.08)' }}>
      <div className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0"
        style={{ background: tint?.bg || '#EAF3FF', color: tint?.fg || '#2F80ED' }}>
        <Icon size={20} />
      </div>
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-widest text-muted">{label}</p>
        <p className="text-lg font-bold text-navy leading-tight truncate">{value}</p>
        {sub && <p className="text-[11px] text-muted truncate">{sub}</p>}
      </div>
    </div>
  );
}

// ── Custom range popover ────────────────────────────────────────────────────
const MAX_CUSTOM_DAYS = 90;

function CustomRangePopover({ anchorRef, initialFrom, initialTo, onApply, onCancel }) {
  const [from, setFrom] = useState(initialFrom || '');
  const [to,   setTo]   = useState(initialTo   || '');
  const popRef = useRef(null);

  // Validation
  const bothSet   = Boolean(from && to);
  const fromValid = from ? !isNaN(new Date(from).getTime()) : true;
  const toValid   = to   ? !isNaN(new Date(to).getTime())   : true;
  const orderOk   = bothSet ? new Date(from) <= new Date(to) : true;
  const tooLong   = bothSet
    ? (new Date(to) - new Date(from)) / DAY_MS > MAX_CUSTOM_DAYS
    : false;
  const canApply  = bothSet && fromValid && toValid && orderOk && !tooLong;

  // Esc + outside click
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onCancel(); };
    const onClick = e => {
      if (popRef.current && !popRef.current.contains(e.target)
          && anchorRef.current && !anchorRef.current.contains(e.target)) {
        onCancel();
      }
    };
    window.addEventListener('keydown', onKey);
    // delay so the opening click doesn't immediately close it
    const t = setTimeout(() => document.addEventListener('mousedown', onClick), 0);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onClick);
      clearTimeout(t);
    };
  }, [onCancel, anchorRef]);

  function submit(e) {
    e.preventDefault();
    if (canApply) onApply(from, to);
  }

  return (
    <form ref={popRef} onSubmit={submit} role="dialog" aria-label="Custom date range"
      className="absolute top-full right-0 mt-2 z-50 w-64 bg-white rounded-2xl p-4 flex flex-col gap-3"
      style={{ boxShadow: '0 12px 40px rgba(30,42,74,0.18)' }}>

      <p className="text-xs font-bold text-navy">Custom date range</p>

      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] font-bold uppercase tracking-widest text-muted">From</span>
        <input type="date" value={from} onChange={e => setFrom(e.target.value)} autoFocus
          className="text-xs px-2.5 py-2 rounded-lg border border-slate-200 bg-slate-50 outline-none focus:border-blue-400" />
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] font-bold uppercase tracking-widest text-muted">To</span>
        <input type="date" value={to} onChange={e => setTo(e.target.value)}
          className="text-xs px-2.5 py-2 rounded-lg border border-slate-200 bg-slate-50 outline-none focus:border-blue-400" />
      </div>

      {bothSet && !orderOk && (
        <p className="text-[11px] text-red-600">"From" cannot be after "To".</p>
      )}
      {bothSet && orderOk && tooLong && (
        <p className="text-[11px] text-red-600">Range cannot exceed {MAX_CUSTOM_DAYS} days.</p>
      )}
      {!bothSet && (
        <p className="text-[11px] text-muted">Set both dates to apply.</p>
      )}

      <div className="flex justify-end gap-2 mt-1">
        <button type="button" onClick={onCancel}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold text-muted hover:bg-slate-100">
          Cancel
        </button>
        <button type="submit" disabled={!canApply}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold text-white disabled:opacity-50"
          style={{ background: '#2F80ED' }}>
          Apply
        </button>
      </div>
    </form>
  );
}

// ── Main component ──────────────────────────────────────────────────────────
export function Analytics() {
  const [searchParams, setSearchParams] = useSearchParams();

  const rangeParam = searchParams.get('range') || DEFAULT_RANGE;
  const range = RANGES.some(r => r.id === rangeParam) ? rangeParam : DEFAULT_RANGE;
  // The custom window that drives fetching comes from the URL (written on
  // Apply in the popover), so the memo below only depends on stable strings.
  const urlFrom = range === 'custom' ? (searchParams.get('from') || '') : '';
  const urlTo   = range === 'custom' ? (searchParams.get('to')   || '') : '';

  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,  setError]  = useState(null);
  const [exporting, setExporting] = useState(null);
  const [toast,   setToast]   = useState(null);
  const toastTimer = useRef(null);
  const dataRef   = useRef(null);   // always-current data, without re-rendering

  // Custom-range popover
  const [showCustom, setShowCustom] = useState(false);

  useEffect(() => { dataRef.current = data; }, [data]);

  const showToast = useCallback((msg, type = 'error') => {
    setToast({ msg, type });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4000);
  }, []);

  // ── Window bounds as stable STRINGS ─────────────────────────────────────
  // Computed via useMemo keyed on the range string + custom date strings only.
  // Never pass Date objects into a dependency array — they are new identities
  // on every render, which caused the page to refetch endlessly.
  const { fromIso, toIso } = useMemo(() => {
    const now = new Date();
    let from, to = now;
    switch (range) {
      case 'today':
        from = new Date(now); from.setHours(0, 0, 0, 0);
        break;
      case '1d':  from = new Date(now.getTime() - 24 * 3600e3);  break;
      case '30d': from = new Date(now.getTime() - 30 * 86400e3); break;
      case 'custom': {
        let f = urlFrom ? new Date(urlFrom) : null;
        let t = urlTo   ? new Date(urlTo)   : null;
        if (f && !isNaN(f) && t && !isNaN(t) && t > f) {
          // include the whole "to" day
          t = new Date(t); t.setHours(23, 59, 59, 999);
          return { fromIso: f.toISOString(), toIso: t.toISOString() };
        }
        return {
          fromIso: new Date(now.getTime() - 7 * 86400e3).toISOString(),
          toIso:   now.toISOString(),
        };
      }
      case '7d':
      default:
        from = new Date(now.getTime() - 7 * 86400e3);
    }
    return { fromIso: from.toISOString(), toIso: to.toISOString() };
  }, [range, urlFrom, urlTo]);   // stable primitives only

  const from = useMemo(() => new Date(fromIso), [fromIso]);
  const to   = useMemo(() => new Date(toIso),   [toIso]);

  // ── Fetch — depends only on the two ISO strings ──────────────────────────
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getAnalytics(fromIso, toIso);
      setData(d);
    } catch (e) {
      setError(e.message || 'Failed to load analytics');
      // If old data is still on screen, surface the failure as a toast
      // instead of unmounting the charts.
      if (dataRef.current) showToast(e.message || 'Failed to refresh analytics', 'error');
    } finally {
      setLoading(false);
    }
  }, [fromIso, toIso, showToast]);

  // One request per filter change. No WebSocket subscription here —
  // this page intentionally ignores live "reading" events.
  useEffect(() => { load(); }, [load]);

  // No state setters during render; the URL sync below only fires on click.

  function setRange(id) {
    if (id === 'custom') {
      // Open (or close, if already open) the popover — nothing moves or resizes.
      setShowCustom(s => !s);
      return;
    }
    if (id === range) return;                      // no change → no URL write, no refetch
    // Preset range: compare before writing so identical values don't refetch.
    const currentRange = searchParams.get('range') || DEFAULT_RANGE;
    if (currentRange === id) return;
    setSearchParams({ range: id }, { replace: false });
  }

  function applyCustom(draftFrom, draftTo) {
    setShowCustom(false);
    const next = { range: 'custom' };
    if (draftFrom) next.from = draftFrom;
    if (draftTo)   next.to = draftTo;
    const appliedFrom = searchParams.get('from');
    const appliedTo   = searchParams.get('to');
    if (range === 'custom' && appliedFrom === draftFrom && appliedTo === draftTo) return;
    setSearchParams(next, { replace: false });
  }

  async function handleExport(kind) {
    setExporting(kind);
    try {
      await downloadCsv(kind, fromIso, toIso);
      showToast(`${kind} report downloaded`, 'success');
    } catch (e) {
      showToast(e.message || `Failed to export ${kind}`, 'error');
    } finally {
      setExporting(null);
    }
  }

  // ── Derived chart data ────────────────────────────────────────────────────
  const deviceIds = useMemo(
    () => (data?.trend || []).map(t => t.device_id),
    [data]
  );

  const perDayStacked = useMemo(() => {
    if (!data?.alerts?.per_day) return [];

    // Chart x-axis: every day of the range, minimum 7 days ending today.
    // Days with zero alerts still appear (value 0), so the chart never
    // collapses into a single huge pillar.
    const endDay   = new Date(to);   endDay.setHours(12, 0, 0, 0);
    let startDay  = new Date(from);  startDay.setHours(12, 0, 0, 0);
    const minStart = new Date(endDay.getTime() - 6 * DAY_MS);   // 7 days incl. end
    if (startDay > minStart) startDay = minStart;
    if (startDay > endDay) startDay = endDay;

    const days = [];
    for (let t = startDay.getTime(); t <= endDay.getTime(); t += DAY_MS) {
      days.push(toISODate(new Date(t)));
    }

    // Seed every day with a row, then add counts per device.
    const byDate = {};
    days.forEach(date => { byDate[date] = { date }; });
    (data.alerts.per_day || []).forEach(({ date, device_id, count }) => {
      const dev = device_id || 'unknown';
      if (!byDate[date]) byDate[date] = { date };   // alert outside chart window
      byDate[date][dev] = (byDate[date][dev] || 0) + count;
    });

    // Sort and attach the display label
    return Object.values(byDate)
      .sort((a, b) => a.date.localeCompare(b.date))
      .map(r => ({ ...r, label: fmtShortDate(`${r.date}T12:00:00`) }));
  }, [data, from, to]);

  const trendMerged = useMemo(() => {
    // Merge per-device series into rows keyed by timestamp for Recharts.
    if (!data?.trend) return { rows: [], safeLow: null, safeHigh: null };
    const idx = new Map();   // t -> row
    let safeLow = null, safeHigh = null;
    data.trend.forEach(t => {
      if (t.safe_low  != null) safeLow  = t.safe_low;
      if (t.safe_high != null) safeHigh = t.safe_high;
      (t.points || []).forEach(p => {
        if (!idx.has(p.t)) idx.set(p.t, { t: p.t });
        idx.get(p.t)[t.device_id] = p.v;
      });
    });
    const rows = [...idx.values()].sort((a, b) => a.t.localeCompare(b.t))
      .map(r => ({ ...r, time: new Date(r.t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }));
    return { rows, safeLow, safeHigh };
  }, [data]);

  const worstDevice = useMemo(() => {
    const list = data?.incidents?.by_device || [];
    return list.length ? list[0] : null;
  }, [data]);

  // ── Render ────────────────────────────────────────────────────────────────
  const isToday = sameLocalDay(from, new Date());
  const customBtnRef = useRef(null);

  // Subtitle: show the chosen dates when a custom range is active
  const subtitle = range === 'custom' && urlFrom && urlTo
    ? `${fmtShortDate(`${urlFrom}T12:00:00`)} → ${fmtShortDate(`${urlTo}T12:00:00`)} (custom) · Oxygen / Medical Air (kg/cm²)`
    : `${fmtDateTime(from)} → ${fmtDateTime(to)} · Oxygen / Medical Air (kg/cm²)`;

  return (
    <div className="p-5 flex flex-col gap-5 page-fade-in">

      {/* Header + date filter */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-lg font-bold text-navy">Analytics &amp; Reports</h1>
          <p className="text-xs text-muted mt-0.5">{subtitle}</p>
        </div>
        {/* Wrapper is always present with a fixed shape — the popover anchors
            to it, so clicking Custom never moves or resizes the header. */}
        <div className="relative flex items-center gap-2 flex-wrap">
          <div className="flex flex-wrap gap-1 p-1.5 rounded-2xl bg-white"
            style={{ boxShadow: '0 4px 24px rgba(80,110,180,0.08)' }}>
            {RANGES.map(({ id, label }) => {
              const active = range === id;
              return (
                <button key={id} ref={id === 'custom' ? customBtnRef : undefined}
                  onClick={() => setRange(id)}
                  className="px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors"
                  style={{
                    background: active ? '#2F80ED' : 'transparent',
                    color: active ? '#fff' : '#8A94A6',
                  }}>
                  {label}
                </button>
              );
            })}
          </div>
          <button onClick={load} disabled={loading} title="Refresh"
            className="p-2 rounded-xl bg-white text-muted hover:text-navy disabled:opacity-50"
            style={{ boxShadow: '0 4px 24px rgba(80,110,180,0.08)' }}>
            <Activity size={15} />
          </button>

          {showCustom && (
            <CustomRangePopover
              anchorRef={customBtnRef}
              initialFrom={urlFrom || (range !== 'custom' ? toISODate(from) : '')}
              initialTo={urlTo || (range !== 'custom' ? toISODate(to) : '')}
              onApply={applyCustom}
              onCancel={() => setShowCustom(false)}
            />
          )}
        </div>
      </div>

      {/* Small "Updating…" indicator — old data stays on screen during refetches */}
      {loading && data && !error && (
        <div className="fixed top-4 right-4 z-40 flex items-center gap-2 px-3 py-2 rounded-xl bg-white text-xs font-semibold text-muted"
          style={{ boxShadow: '0 4px 24px rgba(80,110,180,0.15)' }}>
          <span className="w-3 h-3 rounded-full border-2 border-slate-200 border-t-[#2F80ED] animate-spin" />
          Updating…
        </div>
      )}

      {/* Full-page skeleton only on the very first load (no data yet) */}
      {loading && !data ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-20 rounded-2xl" />)}
          <div className="lg:col-span-4"><Skeleton className="h-64 rounded-2xl" /></div>
          <div className="lg:col-span-4"><Skeleton className="h-64 rounded-2xl" /></div>
        </div>
      ) : error && !data ? (
        <div className="bg-white rounded-2xl p-8 flex flex-col items-center gap-3"
          style={{ boxShadow: '0 4px 24px rgba(80,110,180,0.08)' }}>
          <AlertTriangle size={26} className="text-red-400" />
          <p className="text-sm text-red-600">{error}</p>
          <button onClick={load} className="px-4 py-2 rounded-xl text-xs font-semibold text-white" style={{ background: '#2F80ED' }}>
            Retry
          </button>
        </div>
      ) : !data ? null : (
        <>

        {/* Summary cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard icon={Bell} label="Total alerts"
            value={data.alerts.total}
            sub={isToday ? 'today' : 'in range'}
            tint={{ bg: '#FEE2E2', fg: '#EF4444' }} />
          <StatCard icon={Timer} label="Avg acknowledgement"
            value={fmtDuration(data.alerts.avg_ack_seconds)}
            sub="alert raised → acknowledged"
            tint={{ bg: '#FFFBEB', fg: '#D97706' }} />
          <StatCard icon={CheckCircle} label="Avg resolution"
            value={fmtDuration(data.alerts.avg_resolve_seconds) || '—'}
            sub="alert raised → cleared"
            tint={{ bg: '#DCFCE7', fg: '#16A34A' }} />
          <StatCard icon={FileWarning} label="Open incidents"
            value={data.incidents.open + data.incidents.in_progress}
            sub={`${data.incidents.open} open · ${data.incidents.in_progress} in progress`}
            tint={{ bg: '#EDE9FE', fg: '#8B5CF6' }} />
        </div>

        {/* Alerts per day (stacked by device) + type/device breakdowns */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <Card title="Alerts per Day" subtitle="Stacked by device"
            icon={Bell} className="lg:col-span-2">
            {perDayStacked.length === 0 ? (
              <Empty text="No data in this period." />
            ) : (
              <div style={{ height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={perDayStacked}
                    margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
                    barCategoryGap="25%">
                    <CartesianGrid strokeDasharray="4 4" stroke="#F0F4FF" vertical={false} />
                    <XAxis dataKey="label"
                      tick={{ fontSize: 10, fill: '#8A94A6', fontFamily: 'Poppins' }}
                      tickLine={false} axisLine={false} />
                    <YAxis allowDecimals={false}
                      tick={{ fontSize: 10, fill: '#8A94A6', fontFamily: 'Poppins' }}
                      tickLine={false} axisLine={false} />
                    <Tooltip content={<Tip />} cursor={{ fill: '#F4F7FC', radius: 4 }} />
                    {(data.alerts.by_device || []).map((d, i) => (
                      <Bar key={d.device_id} dataKey={d.device_id} name={d.device_id}
                        stackId="a" fill={colorFor(i)} radius={[3, 3, 0, 0]} maxBarSize={40} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
            {/* device legend */}
            {(data.alerts.by_device || []).length > 0 && (
              <div className="flex flex-wrap gap-2">
                {data.alerts.by_device.map((d, i) => (
                  <span key={d.device_id} className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-full"
                    style={{ background: '#F4F7FC', color: '#1E2A4A' }}>
                    <span className="w-2 h-2 rounded-full" style={{ background: colorFor(i) }} />
                    {d.device_id} · {d.count}
                  </span>
                ))}
              </div>
            )}
          </Card>

          <Card title="Alert Breakdown" subtitle="By type and by device" icon={AlertTriangle}>
            {/* by type */}
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted">By type</p>
            {(data.alerts.by_type || []).length === 0 ? (
              <p className="text-xs text-muted italic">No alerts.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {data.alerts.by_type.map(t => {
                  const st = TYPE_STYLES[t.type] || TYPE_STYLES.OTHER;
                  const pct = data.alerts.total ? Math.round(100 * t.count / data.alerts.total) : 0;
                  return (
                    <div key={t.type}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-semibold text-navy">{st.label}</span>
                        <span className="text-xs font-bold" style={{ color: st.fg }}>{t.count}</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: st.fg }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            {/* by device */}
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted mt-2">By device</p>
            {(data.alerts.by_device || []).length === 0 ? (
              <p className="text-xs text-muted italic">No alerts.</p>
            ) : (
              <div className="flex flex-col gap-1.5">
                {data.alerts.by_device.map((d, i) => (
                  <div key={d.device_id} className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-xs font-medium text-navy">
                      <span className="w-2 h-2 rounded-full" style={{ background: colorFor(i) }} />
                      {d.device_id}
                    </span>
                    <span className="text-xs font-bold text-navy">{d.count}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Device performance table */}
        <Card title="Device Performance" subtitle="Uptime, offline time and message volume in range"
          icon={Activity}>
          {(data.devices || []).length === 0 ? (
            <Empty text="No devices registered." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-100">
                    {['Device', 'Uptime', 'Offline', 'Readings', 'Last message'].map(h => (
                      <th key={h} className="py-2.5 pr-4 text-[10px] font-bold uppercase tracking-widest text-muted whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {data.devices.map((d, i) => (
                    <tr key={d.device_id} className="hover:bg-blue-50/40 transition-colors">
                      <td className="py-3 pr-4">
                        <p className="text-xs font-bold text-navy">{d.device_id}</p>
                        {d.name && <p className="text-[10px] text-muted">{d.name}</p>}
                      </td>
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <div className="w-24 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                            <div className="h-full rounded-full"
                              style={{ width: `${Math.min(100, d.uptime_pct)}%`,
                                       background: d.uptime_pct >= 99 ? '#22C55E' : d.uptime_pct >= 95 ? '#F5A524' : '#EF4444' }} />
                          </div>
                          <span className="text-xs font-semibold text-navy">{d.uptime_pct}%</span>
                        </div>
                      </td>
                      <td className="py-3 pr-4 text-xs font-medium"
                        style={{ color: d.offline_seconds > 3600 ? '#EF4444' : d.offline_seconds > 60 ? '#D97706' : '#6B7280' }}>
                        {fmtDuration(d.offline_seconds)}
                      </td>
                      <td className="py-3 pr-4 text-xs font-semibold text-navy">{d.readings_count}</td>
                      <td className="py-3 pr-4 text-xs text-muted whitespace-nowrap">{fmtDateTime(d.last_message_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Pressure trend (step) */}
        <Card title="Pressure Trend" subtitle="kg/cm² · step chart · dashed lines are safe limits"
          icon={CalendarDays}>
          {trendMerged.rows.length < 2 ? (
            <Empty text="Not enough readings in this period." />
          ) : (
            <>
              <div style={{ height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendMerged.rows} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="4 4" stroke="#F0F4FF" vertical={false} />
                    <XAxis dataKey="time"
                      tick={{ fontSize: 9, fill: '#8A94A6', fontFamily: 'Poppins' }}
                      tickLine={false} axisLine={false} interval="preserveStartEnd" />
                    <YAxis domain={['dataMin - 1', 'dataMax + 1']}
                      tick={{ fontSize: 10, fill: '#8A94A6', fontFamily: 'Poppins' }}
                      tickLine={false} axisLine={false} />
                    <Tooltip content={<Tip />} />
                    {trendMerged.safeLow != null && (
                      <ReferenceLine y={trendMerged.safeLow} stroke="#F59E0B" strokeDasharray="5 3"
                        label={{ value: `safe low ${trendMerged.safeLow}`, position: 'insideBottomLeft', fontSize: 10, fill: '#F59E0B', fontFamily: 'Poppins' }} />
                    )}
                    {trendMerged.safeHigh != null && (
                      <ReferenceLine y={trendMerged.safeHigh} stroke="#8B5CF6" strokeDasharray="5 3"
                        label={{ value: `safe high ${trendMerged.safeHigh}`, position: 'insideTopLeft', fontSize: 10, fill: '#8B5CF6', fontFamily: 'Poppins' }} />
                    )}
                    {deviceIds.map((d, i) => (
                      <Line key={d} type="stepAfter" dataKey={d} name={d}
                        stroke={colorFor(i)} strokeWidth={2} dot={false}
                        connectNulls isAnimationActive={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
              {/* avg / min / max per device */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {data.trend.map((t, i) => (
                  <div key={t.device_id} className="rounded-xl p-2.5 text-center"
                    style={{ background: '#F4F7FC' }}>
                    <p className="text-[10px] font-bold" style={{ color: colorFor(i) }}>{t.device_id}</p>
                    <p className="text-xs font-bold text-navy">
                      avg {t.avg != null ? t.avg.toFixed(2) : '—'}
                    </p>
                    <p className="text-[10px] text-muted">
                      {t.min != null ? t.min.toFixed(2) : '—'} … {t.max != null ? t.max.toFixed(2) : '—'}
                    </p>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>

        {/* Incident analytics + Reports */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Card title="Incidents" subtitle="Created in range" icon={FileWarning}>
            {data.incidents.total === 0 ? (
              <Empty text="No incidents in this period." />
            ) : (
              <>
                <div className="grid grid-cols-4 gap-2">
                  {[
                    { label: 'Open',         value: data.incidents.open,         fg: '#DC2626', bg: '#FEF2F2' },
                    { label: 'In Progress',  value: data.incidents.in_progress,  fg: '#D97706', bg: '#FFFBEB' },
                    { label: 'Closed',       value: data.incidents.closed,       fg: '#16A34A', bg: '#F0FDF4' },
                    { label: 'Avg close',    value: fmtDuration(data.incidents.avg_resolve_seconds), fg: '#2F80ED', bg: '#EAF3FF' },
                  ].map(s => (
                    <div key={s.label} className="rounded-xl p-3 text-center" style={{ background: s.bg }}>
                      <p className="text-lg font-bold leading-tight" style={{ color: s.fg }}>{s.value}</p>
                      <p className="text-[10px] font-semibold text-muted mt-0.5">{s.label}</p>
                    </div>
                  ))}
                </div>
                {worstDevice && (
                  <p className="text-xs text-muted flex items-center gap-1.5">
                    <Info size={12} />
                    Most affected device: <b className="text-navy">{worstDevice.device_id}</b>
                    ({worstDevice.count} incident{worstDevice.count === 1 ? '' : 's'})
                  </p>
                )}
              </>
            )}
          </Card>

          <Card title="Reports" subtitle="CSV downloads for the selected range" icon={Download}>
            <div className="flex flex-col sm:flex-row gap-3">
              {[
                { kind: 'alerts',    label: 'Alert report',    icon: Bell },
                { kind: 'incidents', label: 'Incident report', icon: FileText },
                { kind: 'readings',  label: 'Readings report', icon: Activity },
              ].map(({ kind, label, icon: Icon }) => (
                <button key={kind} onClick={() => handleExport(kind)}
                  disabled={exporting === kind}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-xs font-semibold text-white disabled:opacity-60 transition-colors"
                  style={{ background: '#2F80ED' }}>
                  {exporting === kind
                    ? 'Downloading…'
                    : <><Icon size={14} /> {label} <Download size={12} className="opacity-80" /></>}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-muted">
              Exports include the full window {fmtDateTime(from)} → {fmtDateTime(to)}.
              Readings are limited to Oxygen / Medical Air (kg/cm²).
            </p>
          </Card>
        </div>

        </>
      )}

      {/* Error toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2.5 px-4 py-3 rounded-xl text-xs font-semibold text-white shadow-2xl"
          style={{ background: toast.type === 'success' ? '#16A34A' : '#EF4444' }}>
          {toast.type === 'success'
            ? <CheckCircle size={14} />
            : <AlertTriangle size={14} />}
          {toast.msg}
          <button onClick={() => setToast(null)} className="ml-1 opacity-80 hover:opacity-100">
            <X size={12} />
          </button>
        </div>
      )}
    </div>
  );
}

export default Analytics;
