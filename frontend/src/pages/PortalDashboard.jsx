/**
 * pages/PortalDashboard.jsx
 * =========================
 * Full dashboard page — layout matches lead-spec.md:
 *   1. Title + system status chip
 *   2. Summary stat cards (devices + alerts)
 *   3. Device overview cards
 *   4. Oxygen pressure trend chart (step, per-device, time-filtered)
 *   5. Recent alerts (last 5, all statuses)
 *   6. Recent activity
 *
 * Receives: summary, devices, alerts (active), activity, loading
 * from PortalApp → usePortalData.
 * Chart data is fetched independently and re-fetched on WS events
 * via the reload prop.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts';
import {
  Activity, Bell, Cpu, WifiOff, CheckCircle,
  AlertTriangle, Clock, ChevronRight, Wifi,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { StatCard }   from '../components/cards/StatCard';
import { StatusPill } from '../components/ui/StatusPill';
import { Skeleton }   from '../components/ui/Skeleton';
import { getReadings, getAlerts } from '../api/portal';

// ── Shared design tokens ──────────────────────────────────────────────────────
const CARD         = { boxShadow: '0 4px 24px rgba(80,110,180,0.08)' };
const DEVICE_COLORS = ['#2F80ED', '#22C55E', '#F5A524', '#F0386B', '#8B5CF6', '#06B6D4'];

// Tailwind classes applied to every clickable stat card wrapper.
// outline-offset-2 and focus-visible:ring keep keyboard navigation visible.
const STAT_LINK =
  'block rounded-2xl transition-all duration-150 cursor-pointer ' +
  'hover:-translate-y-0.5 hover:shadow-[0_8px_32px_rgba(80,110,180,0.14)] ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2';

// ── Helpers ───────────────────────────────────────────────────────────────────
function safeDate(raw) {
  if (!raw) return null;
  const d = raw instanceof Date ? raw : new Date(raw);
  return isNaN(d.getTime()) ? null : d;
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
  if (h < 24) return `${h}h ${m % 60}m ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function fmtTime(isoString) {
  const d = safeDate(isoString);
  if (!d) return '';
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Status → colour config used in multiple places
const STATUS_CFG = {
  NORMAL:     { bg: '#F0FDF4', color: '#16A34A', border: 'transparent' },
  CRITICAL:   { bg: '#FEF2F2', color: '#EF4444', border: '#EF4444'     },
  OFFLINE:    { bg: '#F4F7FC', color: '#8A94A6', border: 'transparent' },
  UNREADABLE: { bg: '#FFFBEB', color: '#D97706', border: '#D97706'     },
  UNKNOWN:    { bg: '#F4F7FC', color: '#8A94A6', border: 'transparent' },
};

function StatusChip({ status, size = 'sm' }) {
  const s   = (status || 'UNKNOWN').toUpperCase();
  const cfg = STATUS_CFG[s] || STATUS_CFG.UNKNOWN;
  const px  = size === 'xs' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs';
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-bold ${px}`}
      style={{ background: cfg.bg, color: cfg.color }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: cfg.color }} />
      {s}
    </span>
  );
}

function GaugeStatusChip({ status }) {
  const MAP = {
    OK:        { bg: '#F0FDF4', color: '#16A34A' },
    NEAR_LOW:  { bg: '#FFFBEB', color: '#D97706' },
    NEAR_HIGH: { bg: '#FFFBEB', color: '#D97706' },
    LOW:       { bg: '#FEF2F2', color: '#EF4444' },
    HIGH:      { bg: '#FEF2F2', color: '#EF4444' },
    CRITICAL:  { bg: '#FEF2F2', color: '#EF4444' },
    READ:      { bg: '#F4F7FC', color: '#8A94A6' },
    UNCERTAIN: { bg: '#F4F7FC', color: '#8A94A6' },
  };
  const s   = (status || 'UNCERTAIN').toUpperCase();
  const cfg = MAP[s] || { bg: '#F4F7FC', color: '#8A94A6' };
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[9px] font-bold"
      style={{ background: cfg.bg, color: cfg.color }}>
      {s}
    </span>
  );
}

// ── 1. System status chip (top of page) ─────────────────────────────────────
function SystemStatusChip({ summary }) {
  if (!summary) return null;
  const { devices = {} } = summary;
  let label, color, bg;
  if (devices.critical > 0) {
    label = 'Tablet: Critical'; color = '#EF4444'; bg = '#FEF2F2';
  } else if (devices.offline > 0) {
    label = 'Tablet: Offline';  color = '#F59E0B'; bg = '#FFFBEB';
  } else {
    label = 'Tablet: Normal';   color = '#22C55E'; bg = '#F0FDF4';
  }
  return (
    <span
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold cursor-default"
      style={{ background: bg, color }}
      title="Status of the monitoring tablets"
    >
      <span className="w-2 h-2 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

// ── 3. Device overview card ──────────────────────────────────────────────────
function DeviceCard({ device }) {
  const gauges   = device.gauges || [];
  const isCrit   = (device.status || '').toUpperCase() === 'CRITICAL';
  const isOffline = (device.status || '').toUpperCase() === 'OFFLINE';

  return (
    <div
      className="bg-white rounded-2xl p-4 flex flex-col gap-3 transition-shadow hover:shadow-md"
      style={{
        ...CARD,
        borderLeft: isCrit ? '4px solid #EF4444' : '4px solid transparent',
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-bold text-navy leading-none truncate">
            {device.name || device.device_id}
          </p>
          <p className="text-[11px] text-muted mt-0.5 truncate">
            {device.location || device.device_id}
          </p>
        </div>
        <StatusChip status={device.status} size="xs" />
      </div>

      {/* Gauge tiles */}
      {gauges.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          {gauges.map((g, i) => (
            <div key={i}
              className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-xl"
              style={{ background: '#F8FAFF' }}>
              <span className="text-[11px] font-semibold text-muted truncate">
                {g.gas || '—'}
                {g.number != null && <span className="ml-1 opacity-60">#{g.number}</span>}
              </span>
              <span className="text-xs font-bold text-navy">
                {g.reading != null ? `${g.reading} ${g.unit || ''}`.trim() : '—'}
              </span>
              <GaugeStatusChip status={g.status} />
            </div>
          ))}
        </div>
      ) : (
        <p className="text-[11px] text-muted italic">No gauges in latest reading</p>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-1">
        <p className="text-[10px] text-muted">
          {device.last_seen_at ? `Updated ${timeAgo(device.last_seen_at)}` : 'Never seen'}
        </p>
        <span className={`flex items-center gap-1 text-[10px] font-semibold ${isOffline ? 'text-muted' : 'text-green-600'}`}>
          {isOffline
            ? <><WifiOff size={10} /> Offline</>
            : <><Wifi size={10} /> Connected</>}
        </span>
      </div>
    </div>
  );
}

// ── 4. Pressure trend chart ──────────────────────────────────────────────────
const TIME_OPTS = [
  { label: '15 min', minutes: 15  },
  { label: '1 h',    minutes: 60  },
  { label: '24 h',   minutes: 1440 },
];

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl p-3 text-xs"
      style={{ background: '#fff', border: '1px solid #E8EEFA',
               boxShadow: '0 8px 24px rgba(80,110,180,0.12)', minWidth: 130 }}>
      <p className="mb-2 font-medium text-muted">{label}</p>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 mb-1">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color || p.stroke }} />
          <span className="text-navy font-semibold">
            {p.value != null ? `${Number(p.value).toFixed(2)} ${p.payload?.unit || 'kg/cm²'}` : '—'}
          </span>
        </div>
      ))}
    </div>
  );
}

function PressureTrendChart({ devices, wsRevision }) {
  const [minutes,     setMinutes]     = useState(60);
  const [selectedId,  setSelectedId]  = useState(null);
  const [chartData,   setChartData]   = useState([]);
  const [safeLow,     setSafeLow]     = useState(null);
  const [safeHigh,    setSafeHigh]    = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState(null);

  // Auto-select first device
  useEffect(() => {
    if (devices.length > 0 && selectedId === null) {
      setSelectedId(devices[0].device_id);
    }
  }, [devices, selectedId]);

  // Pull safe thresholds from device gauge data (read-only from latest reading)
  useEffect(() => {
    if (!selectedId) return;
    const dev = devices.find(d => d.device_id === selectedId);
    if (!dev) return;
    const oGauge = (dev.gauges || []).find(g => (g.gas || '').toUpperCase() === 'OXYGEN');
    setSafeLow( oGauge?.safe_low  ?? null);
    setSafeHigh(oGauge?.safe_high ?? null);
  }, [selectedId, devices]);

  const fetchChart = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    try {
      const rows = await getReadings(selectedId, 'OXYGEN', minutes);
      // Build step-chart data: { time, reading, unit }
      const data = (rows || []).map(r => ({
        time:    fmtTime(r.timestamp),
        reading: r.reading,
        unit:    r.unit || 'kg/cm²',
        status:  r.status,
      }));
      setChartData(data);
    } catch (e) {
      setError(e.message || 'Failed to load readings');
    } finally {
      setLoading(false);
    }
  }, [selectedId, minutes]);

  // Re-fetch when device/time changes or WS fires
  useEffect(() => { fetchChart(); }, [fetchChart, wsRevision]);

  if (devices.length === 0) return null;

  const unit = chartData[0]?.unit || 'kg/cm²';

  return (
    <div className="bg-white rounded-2xl p-5 flex flex-col gap-4" style={CARD}>
      {/* Title row */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-sm font-semibold text-navy">Oxygen Pressure Trend</h2>
          <p className="text-[11px] text-muted mt-0.5">
            Step chart · OXYGEN gauges · {unit}
            {safeLow  != null && ` · safe low ${safeLow}`}
            {safeHigh != null && ` · safe high ${safeHigh}`}
          </p>
        </div>

        {/* Time filter */}
        <div className="flex items-center gap-1 p-1 rounded-xl bg-slate-50">
          {TIME_OPTS.map(opt => (
            <button key={opt.minutes}
              onClick={() => setMinutes(opt.minutes)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
              style={{
                background: minutes === opt.minutes ? '#2F80ED' : 'transparent',
                color:      minutes === opt.minutes ? '#fff'    : '#8A94A6',
              }}>
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Device selector (only when >1 device) */}
      {devices.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {devices.map((d, i) => (
            <button key={d.device_id}
              onClick={() => setSelectedId(d.device_id)}
              className="flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-semibold transition-all border"
              style={{
                background:   selectedId === d.device_id ? DEVICE_COLORS[i % DEVICE_COLORS.length] : '#fff',
                color:        selectedId === d.device_id ? '#fff' : '#8A94A6',
                borderColor:  selectedId === d.device_id ? DEVICE_COLORS[i % DEVICE_COLORS.length] : '#E8EEFA',
              }}>
              <span className="w-2 h-2 rounded-full"
                style={{ background: selectedId === d.device_id ? '#fff' : DEVICE_COLORS[i % DEVICE_COLORS.length] }} />
              {d.name || d.device_id}
            </button>
          ))}
        </div>
      )}

      {/* Chart */}
      {loading ? (
        <Skeleton className="h-48 w-full" />
      ) : error ? (
        <div className="flex items-center justify-center h-48 rounded-xl bg-red-50">
          <p className="text-xs text-red-600 font-medium">{error}</p>
        </div>
      ) : chartData.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-48 gap-2">
          <Activity size={28} className="text-slate-200" />
          <p className="text-sm text-muted">No readings in this period</p>
        </div>
      ) : (
        <div style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="4 4" stroke="#F0F4FF" vertical={false} />
              <XAxis dataKey="time"
                tick={{ fontSize: 10, fill: '#8A94A6', fontFamily: 'Poppins,sans-serif' }}
                tickLine={false} axisLine={false} interval="preserveStartEnd" />
              <YAxis
                tick={{ fontSize: 10, fill: '#8A94A6', fontFamily: 'Poppins,sans-serif' }}
                tickLine={false} axisLine={false}
                label={{ value: unit, angle: -90, position: 'insideLeft',
                         style: { fontSize: 9, fill: '#8A94A6', fontFamily: 'Poppins,sans-serif' },
                         dx: 14 }} />
              <Tooltip content={<ChartTooltip />} />
              {safeLow != null && (
                <ReferenceLine y={safeLow} stroke="#F59E0B" strokeDasharray="5 3"
                  label={{ value: `Low ${safeLow}`, position: 'insideBottomLeft',
                           fontSize: 9, fill: '#F59E0B', fontFamily: 'Poppins,sans-serif' }} />
              )}
              {safeHigh != null && (
                <ReferenceLine y={safeHigh} stroke="#8B5CF6" strokeDasharray="5 3"
                  label={{ value: `High ${safeHigh}`, position: 'insideTopLeft',
                           fontSize: 9, fill: '#8B5CF6', fontFamily: 'Poppins,sans-serif' }} />
              )}
              <Line
                type="stepAfter"
                dataKey="reading"
                stroke="#2F80ED"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0 }}
                isAnimationActive={false}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

// ── 5. Recent alerts card ────────────────────────────────────────────────────
const SEVERITY_CFG = {
  CRITICAL:   { bg: '#FEF2F2', color: '#EF4444' },
  HIGH:       { bg: '#FEF2F2', color: '#EF4444' },
  OFFLINE:    { bg: '#F4F7FC', color: '#8A94A6' },
  UNREADABLE: { bg: '#FFFBEB', color: '#D97706' },
  MEDIUM:     { bg: '#FFFBEB', color: '#D97706' },
  LOW:        { bg: '#EAF3FF', color: '#2F80ED' },
};

function SeverityBadge({ severity }) {
  if (!severity) return null;
  const s = severity.toUpperCase();
  const cfg = SEVERITY_CFG[s] || { bg: '#F4F7FC', color: '#8A94A6' };
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold"
      style={{ background: cfg.bg, color: cfg.color }}>
      {s}
    </span>
  );
}

function AlertStatusBadge({ status }) {
  const cfg = {
    active:       { bg: '#FEF2F2', color: '#EF4444' },
    acknowledged: { bg: '#FFFBEB', color: '#D97706' },
    resolved:     { bg: '#F0FDF4', color: '#16A34A' },
  };
  const c = cfg[status] || { bg: '#F4F7FC', color: '#8A94A6' };
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold capitalize"
      style={{ background: c.bg, color: c.color }}>
      {status}
    </span>
  );
}

function RecentAlertsCard({ wsRevision }) {
  const [recentAlerts, setRecentAlerts] = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState(null);

  const fetch5 = useCallback(async () => {
    setError(null);
    try {
      const data = await getAlerts('all');
      setRecentAlerts((data || []).slice(0, 5));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch5(); }, [fetch5, wsRevision]);

  const borderColor = {
    active:       '#EF4444',
    acknowledged: '#F59E0B',
    resolved:     '#22C55E',
  };

  return (
    <div className="bg-white rounded-2xl flex flex-col" style={{ ...CARD, maxHeight: 320 }}>
      {/* Sticky header */}
      <div className="flex items-center justify-between px-5 pt-5 pb-3 shrink-0">
        <h2 className="text-sm font-semibold text-navy">Recent Alerts</h2>
        <Link to="/alerts"
          className="flex items-center gap-1 text-xs font-semibold text-primary hover:underline">
          View all <ChevronRight size={13} />
        </Link>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto px-5 pb-5" style={{ scrollbarWidth: 'thin' }}>
        {loading ? (
          <div className="flex flex-col gap-2">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-14" />)}
          </div>
        ) : error ? (
          <p className="text-xs text-red-500 py-4 text-center">{error}</p>
        ) : recentAlerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 gap-2">
            <CheckCircle size={24} className="text-green-400" />
            <p className="text-sm text-muted">No alerts yet</p>
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {recentAlerts.map(a => {
              const reasons = Array.isArray(a.reasons) ? a.reasons : [];
              const firstReason = reasons[0] || '';
              return (
                <li key={a.id}
                  className="rounded-xl px-3 py-2.5 border-l-4"
                  style={{
                    background:  '#F8FAFF',
                    borderColor: borderColor[a.status] || '#8A94A6',
                  }}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-xs font-bold text-navy">{a.device_id}</span>
                        <SeverityBadge severity={a.severity} />
                        <AlertStatusBadge status={a.status} />
                      </div>
                      <p className="text-[11px] text-muted mt-0.5 truncate">
                        {firstReason || (a.alert_type || '').replace(/_/g, ' ')}
                      </p>
                    </div>
                    <span className="text-[10px] text-muted shrink-0 mt-0.5">
                      {timeAgo(a.started_at)}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

// ── 6. Activity card ─────────────────────────────────────────────────────────
const ACT_ICON_CFG = {
  alert_raised:        { bg: '#FEF2F2', color: '#EF4444',  Icon: Bell          },
  alert_acknowledged:  { bg: '#FFFBEB', color: '#D97706',  Icon: AlertTriangle },
  alert_resolved:      { bg: '#F0FDF4', color: '#16A34A',  Icon: CheckCircle   },
  alert_cleared:       { bg: '#F0FDF4', color: '#16A34A',  Icon: CheckCircle   },
  device_offline:      { bg: '#F4F7FC', color: '#8A94A6',  Icon: WifiOff       },
  device_online:       { bg: '#F0FDF4', color: '#16A34A',  Icon: Wifi          },
  default:             { bg: '#EAF3FF', color: '#2F80ED',  Icon: Activity      },
};

function ActivityCard({ activity = [], loading }) {
  return (
    <div className="bg-white rounded-2xl flex flex-col" style={{ ...CARD, maxHeight: 320 }}>
      {/* Sticky header */}
      <div className="px-5 pt-5 pb-3 shrink-0">
        <h2 className="text-sm font-semibold text-navy">Recent Activity</h2>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto px-5 pb-5" style={{ scrollbarWidth: 'thin' }}>
        {loading ? (
          <div className="flex flex-col gap-2">
            {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-10" />)}
          </div>
        ) : activity.length === 0 ? (
          <p className="text-sm text-muted text-center py-8">No recent activity.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-slate-50">
            {activity.slice(0, 20).map(item => {
              const key = item.event_type?.toLowerCase() || 'default';
              const cfg = ACT_ICON_CFG[key] || ACT_ICON_CFG.default;
              const { Icon } = cfg;
              return (
                <li key={item.id} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
                    style={{ background: cfg.bg }}>
                    <Icon size={12} style={{ color: cfg.color }} strokeWidth={2.2} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-navy leading-snug">
                      {(item.event_type || '').replace(/_/g, ' ')}
                      {item.device_id ? ` — ${item.device_id}` : ''}
                    </p>
                    {item.detail && (
                      <p className="text-[10px] text-muted mt-0.5 truncate">{item.detail}</p>
                    )}
                    <p className="text-[9px] text-muted mt-0.5">{timeAgo(item.created_at)}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

// ── Root component ───────────────────────────────────────────────────────────
export default function PortalDashboard({
  summary, devices = [], alerts = [], activity = [], loading,
}) {
  const devStats   = summary?.devices || {};
  const alertStats = summary?.alerts  || {};

  // Incrementing counter used to signal chart/alerts sub-cards to re-fetch
  // when the parent triggers a reload (WS event). We derive it from the
  // alerts array identity so it ticks on every reload without prop drilling.
  const wsRevisionRef = useRef(0);
  const prevAlertsRef = useRef(alerts);
  if (alerts !== prevAlertsRef.current) {
    wsRevisionRef.current += 1;
    prevAlertsRef.current = alerts;
  }
  const wsRevision = wsRevisionRef.current;

  return (
    <div className="p-5 flex flex-col gap-5 page-fade-in">

      {/* ── 1. Title + status chip ─────────────────────────── */}
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-navy">Dashboard</h1>
        <SystemStatusChip summary={summary} />
      </div>

      {/* ── 2. Summary cards ──────────────────────────────── */}
      {/* Device cards → /live (with optional ?status= filter) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Link to="/live" className={STAT_LINK}>
          <StatCard value={loading ? '…' : devStats.total    ?? 0} label="Total Devices"    Icon={Cpu}           iconBg="bg-blue-50"   iconColor="text-primary"    />
        </Link>
        <Link to="/live" className={STAT_LINK}>
          <StatCard value={loading ? '…' : devStats.normal   ?? 0} label="Normal Devices"   Icon={CheckCircle}   iconBg="bg-green-50"  iconColor="text-green-600"  />
        </Link>
        <Link to="/live?status=critical" className={STAT_LINK}>
          <StatCard value={loading ? '…' : devStats.critical ?? 0} label="Critical Devices" Icon={AlertTriangle} iconBg="bg-red-50"    iconColor="text-red-500"    />
        </Link>
        <Link to="/live?status=offline" className={STAT_LINK}>
          <StatCard value={loading ? '…' : devStats.offline  ?? 0} label="Offline Devices"  Icon={WifiOff}       iconBg="bg-slate-100" iconColor="text-slate-400"  />
        </Link>
      </div>

      {/* Alert cards → /alerts?status=... */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Link to="/alerts?status=active" className={STAT_LINK}>
          <StatCard value={loading ? '…' : alertStats.active       ?? 0} label="Active Alerts"  Icon={Bell}        iconBg="bg-red-50"    iconColor="text-red-500"    />
        </Link>
        <Link to="/alerts?status=acknowledged" className={STAT_LINK}>
          <StatCard value={loading ? '…' : alertStats.acknowledged ?? 0} label="Acknowledged"   Icon={Clock}       iconBg="bg-amber-50"  iconColor="text-amber-500"  />
        </Link>
        <Link to="/alerts?status=resolved" className={STAT_LINK}>
          <StatCard value={loading ? '…' : alertStats.resolved     ?? 0} label="Resolved"       Icon={CheckCircle} iconBg="bg-green-50"  iconColor="text-green-600"  />
        </Link>
        <Link to="/alerts?status=all" className={STAT_LINK}>
          <StatCard value={loading ? '…' : alertStats.total        ?? 0} label="Total Alerts"   Icon={Activity}    iconBg="bg-purple-50" iconColor="text-purple-500" />
        </Link>
      </div>

      {/* ── 3. Device overview cards ───────────────────────── */}
      <div>
        <h2 className="text-sm font-semibold text-navy mb-3">Device Overview</h2>
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-36" />)}
          </div>
        ) : devices.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 gap-3 bg-white rounded-2xl" style={CARD}>
            <Cpu size={28} className="text-muted opacity-30" />
            <p className="text-sm text-muted">No devices registered yet.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {devices.map(d => <DeviceCard key={d.device_id} device={d} />)}
          </div>
        )}
      </div>

      {/* ── 4. Pressure trend chart ────────────────────────── */}
      {devices.length > 0 && (
        <PressureTrendChart devices={devices} wsRevision={wsRevision} />
      )}

      {/* ── 5 + 6. Recent alerts + activity side by side ─── */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <RecentAlertsCard wsRevision={wsRevision} />
        <ActivityCard activity={activity} loading={loading} />
      </div>

    </div>
  );
}
