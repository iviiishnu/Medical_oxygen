/**
 * pages/LiveMonitoring.jsx
 * ========================
 * Live Monitoring page — per lead spec:
 *
 *   1. Device selector row  — all devices, selectable tabs, URL sync ?device=
 *   2. Live gauge tiles     — SVG semicircular gauge per gauge in latest reading
 *   3. Reading history      — step chart, 15 min / 1 h / 24 h, per-unit axes
 *   4. Configure device     — PATCH modal (name + location), Viewer-hidden
 *   5. Thresholds panel     — read-only, expandable, from latest gauge data
 *   6. Camera feed          — placeholder card
 *
 * Data sources:
 *   • Device list + latest gauges  → usePortalData().devices (refreshed via WS)
 *   • Reading history              → GET /api/devices/{id}/readings  (local fetch)
 *   • Device config update         → PATCH /api/devices/{id}
 *
 * Live updates: when a WS "reading" or "alert" event arrives, usePortalData
 * reloads its devices array.  The page detects that via a prop-equality check
 * and re-renders gauge tiles automatically.  The history chart re-fetches too.
 */
import {
  useState, useEffect, useCallback, useRef, useMemo,
} from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts';
import {
  Wifi, WifiOff, AlertTriangle, ChevronDown, ChevronUp,
  Settings, Camera, X, CheckCircle, Info,
} from 'lucide-react';
import { getReadings, updateDevice } from '../api/portal';
import { useAuth }    from '../hooks/useAuth';
import { Skeleton }   from '../components/ui/Skeleton';

// ─────────────────────────────────────────────────────────────────────────────
// Design tokens (match Dashboard)
// ─────────────────────────────────────────────────────────────────────────────
const CARD = { boxShadow: '0 4px 24px rgba(80,110,180,0.08)' };

const STATUS_CFG = {
  NORMAL:     { dot: '#22C55E', bg: '#F0FDF4', text: '#16A34A' },
  CRITICAL:   { dot: '#EF4444', bg: '#FEF2F2', text: '#EF4444' },
  OFFLINE:    { dot: '#94A3B8', bg: '#F4F7FC', text: '#6B7280' },
  UNREADABLE: { dot: '#F59E0B', bg: '#FFFBEB', text: '#D97706' },
  UNKNOWN:    { dot: '#94A3B8', bg: '#F4F7FC', text: '#6B7280' },
};

const GAUGE_STATUS_CFG = {
  OK:        { bg: '#F0FDF4', color: '#16A34A' },
  NEAR_LOW:  { bg: '#FFFBEB', color: '#D97706' },
  NEAR_HIGH: { bg: '#FFFBEB', color: '#D97706' },
  LOW:       { bg: '#FEF2F2', color: '#EF4444' },
  HIGH:      { bg: '#FEF2F2', color: '#EF4444' },
  CRITICAL:  { bg: '#FEF2F2', color: '#EF4444' },
  READ:      { bg: '#F4F7FC', color: '#8A94A6' },
  UNCERTAIN: { bg: '#F4F7FC', color: '#8A94A6' },
};

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
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
  return `${h}h ${m % 60}m ago`;
}

function fmtTime(isoString) {
  const d = safeDate(isoString);
  if (!d) return '';
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. Device selector row
// ─────────────────────────────────────────────────────────────────────────────
function DeviceSelectorRow({ devices, selectedId, onSelect }) {
  if (!devices.length) return null;

  return (
    <div className="flex flex-wrap gap-2" role="tablist" aria-label="Select device">
      {devices.map(dev => {
        const cfg    = STATUS_CFG[(dev.status || 'UNKNOWN').toUpperCase()] || STATUS_CFG.UNKNOWN;
        const active = dev.device_id === selectedId;
        return (
          <button
            key={dev.device_id}
            role="tab"
            aria-selected={active}
            onClick={() => onSelect(dev.device_id)}
            className="flex items-center gap-2.5 px-4 py-2.5 rounded-2xl text-left transition-all border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
            style={{
              background:  active ? '#2F80ED' : '#fff',
              borderColor: active ? '#2F80ED' : '#E8EEFA',
              boxShadow:   active ? '0 4px 16px rgba(47,128,237,0.25)' : '0 2px 8px rgba(80,110,180,0.06)',
            }}
          >
            {/* Status dot */}
            <span
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{ background: active ? '#fff' : cfg.dot }}
            />
            <div className="text-left">
              <p className="text-xs font-bold leading-none"
                style={{ color: active ? '#fff' : '#1E2A4A' }}>
                {dev.name || dev.device_id}
              </p>
              {dev.location && (
                <p className="text-[10px] mt-0.5 leading-none"
                  style={{ color: active ? 'rgba(255,255,255,0.75)' : '#8A94A6' }}>
                  {dev.location}
                </p>
              )}
              <p className="text-[10px] mt-0.5 leading-none"
                style={{ color: active ? 'rgba(255,255,255,0.65)' : '#8A94A6' }}>
                {dev.last_seen_at ? timeAgo(dev.last_seen_at) : 'Never seen'}
              </p>
            </div>
          </button>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 2a. Reading colour by gauge status
// ─────────────────────────────────────────────────────────────────────────────
function readingColor(st) {
  if (!st) return '#8A94A6';
  switch (st.toUpperCase()) {
    case 'OK':                      return '#16A34A';
    case 'NEAR_LOW': case 'NEAR_HIGH': return '#D97706';
    case 'LOW': case 'HIGH': case 'CRITICAL': return '#EF4444';
    case 'READ':                    return '#1E2A4A';
    default:                        return '#8A94A6'; // UNCERTAIN
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 2b. Horizontal range bar
// ─────────────────────────────────────────────────────────────────────────────
/**
 * Renders a full-width rounded bar divided into coloured zones, with a small
 * triangle marker at the current reading position.
 *
 * Scale:
 *   min = 0
 *   max = safe_high * 1.4   (if safe_high exists)
 *       = max(reading * 1.2, safe_low * 2)  (otherwise)
 *
 * Zone layout (left → right):
 *   red band  : 0 → safe_critical
 *   amber band: safe_critical → safe_low  (or just safe_critical → safe_low when no safe_critical)
 *   green zone: safe_low → safe_high  (or safe_low → end when no safe_high)
 *   amber band: safe_high - safe_buffer → safe_high  (thin, skipped if safe_high null)
 *   red  band : safe_high → max  (skipped if safe_high null)
 *
 * null limits → skip that zone.
 */
function RangeBar({ reading, unit, status, safe_low, safe_high, safe_critical, safe_buffer }) {
  const st = (status || 'UNCERTAIN').toUpperCase();

  // Compute scale max
  const scaleMax = (() => {
    if (safe_high != null) return safe_high * 1.4;
    const base = Math.max(
      reading  != null ? reading  * 1.2 : 0,
      safe_low != null ? safe_low * 2   : 0,
    );
    return base > 0 ? base : 10; // fallback
  })();

  // Convert value to % of bar width, clamped 0–100
  const pct = (v) => Math.min(Math.max((v / scaleMax) * 100, 0), 100);

  // Build zone segments: each is { left%, width%, color }
  const segments = [];

  if (safe_critical != null && safe_low != null) {
    // Red: 0 → safe_critical
    segments.push({ left: 0, width: pct(safe_critical), color: '#FCA5A5' });
    // Amber: safe_critical → safe_low
    segments.push({ left: pct(safe_critical), width: pct(safe_low) - pct(safe_critical), color: '#FCD34D' });
  } else if (safe_low != null) {
    // Red: 0 → safe_low  (no safe_critical)
    segments.push({ left: 0, width: pct(safe_low), color: '#FCA5A5' });
  } else if (safe_critical != null) {
    segments.push({ left: 0, width: pct(safe_critical), color: '#FCA5A5' });
  }

  // Green: safe_low (or safe_critical, or 0) → safe_high (or end)
  const greenStart = safe_low ?? safe_critical ?? 0;
  const greenEnd   = safe_high ?? scaleMax;
  if (greenEnd > greenStart) {
    segments.push({ left: pct(greenStart), width: pct(greenEnd) - pct(greenStart), color: '#86EFAC' });
  }

  // Amber upper buffer + Red above safe_high
  if (safe_high != null) {
    if (safe_buffer != null && safe_buffer > 0) {
      const bufStart = safe_high - safe_buffer;
      if (bufStart > greenStart) {
        // Trim the green and add amber
        const lastGreen = segments[segments.length - 1];
        if (lastGreen && lastGreen.color === '#86EFAC') {
          lastGreen.width = pct(bufStart) - lastGreen.left;
        }
        segments.push({ left: pct(bufStart), width: pct(safe_high) - pct(bufStart), color: '#FCD34D' });
      }
    }
    // Red: safe_high → scaleMax
    if (pct(safe_high) < 100) {
      segments.push({ left: pct(safe_high), width: 100 - pct(safe_high), color: '#FCA5A5' });
    }
  }

  // Fallback: if no segments were built (all nulls), show a single grey bar
  if (segments.length === 0) {
    segments.push({ left: 0, width: 100, color: '#E2E8F0' });
  }

  // Marker position, clamped 0–100 and smooth-transitioned via CSS
  const markerPct = reading != null ? Math.min(Math.max(pct(reading), 0), 100) : null;

  return (
    <div className="w-full flex flex-col gap-0" aria-hidden="true">
      {/* Bar */}
      <div className="relative w-full" style={{ height: 14 }}>
        {/* Track background */}
        <div className="absolute inset-0 rounded-full overflow-hidden flex">
          {segments.map((s, i) => (
            <div
              key={i}
              style={{
                position: 'absolute',
                left:  `${s.left}%`,
                width: `${Math.max(s.width, 0)}%`,
                top: 0, bottom: 0,
                background: s.color,
              }}
            />
          ))}
        </div>

        {/* Marker triangle */}
        {markerPct != null && (
          <div
            style={{
              position:   'absolute',
              left:       `${markerPct}%`,
              top:        '50%',
              transform:  'translate(-50%, -50%)',
              transition: 'left 0.4s ease',
              zIndex:     2,
            }}
          >
            {/* Down-pointing triangle */}
            <div style={{
              width: 0, height: 0,
              borderLeft:   '5px solid transparent',
              borderRight:  '5px solid transparent',
              borderTop:    '8px solid #1E2A4A',
            }} />
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 2c. Gauge tile (one per gauge in the latest message)
// ─────────────────────────────────────────────────────────────────────────────
function GaugeTile({ gauge }) {
  const {
    gas, number, reading, unit,
    status, safe_low, safe_high, safe_critical, safe_buffer,
  } = gauge;

  const st    = (status || 'UNCERTAIN').toUpperCase();
  const cfg   = GAUGE_STATUS_CFG[st] || GAUGE_STATUS_CFG.UNCERTAIN;
  const color = readingColor(st);

  // Build the safe-range text line
  const safeRangeLine = (() => {
    if (safe_low != null && safe_high != null)
      return `Safe range ${safe_low} – ${safe_high} ${unit || ''}`;
    if (safe_low != null && safe_high == null)
      return `Safe: at least ${safe_low} ${unit || ''}`;
    if (safe_high != null && safe_low == null)
      return `Safe: up to ${safe_high} ${unit || ''}`;
    return 'No safe range set';
  })();

  const criticalLine = safe_critical != null
    ? `Critical below ${safe_critical} ${unit || ''}`
    : null;

  const displayReading = st === 'UNCERTAIN' || reading == null ? '—' : reading;

  return (
    <div className="bg-white rounded-2xl p-4 flex flex-col gap-3" style={CARD}>
      {/* Header: gas name, gauge number, status badge */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-bold text-navy">{gas || 'Unknown gas'}</p>
          {number != null && <p className="text-[10px] text-muted">Gauge #{number}</p>}
        </div>
        <span
          className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0"
          style={{ background: cfg.bg, color: cfg.color }}>
          {st}
        </span>
      </div>

      {/* Big reading number */}
      <div className="flex items-baseline gap-1.5">
        <span className="text-3xl font-extrabold leading-none" style={{ color }}>
          {displayReading}
        </span>
        {reading != null && unit && (
          <span className="text-sm font-semibold text-muted">{unit}</span>
        )}
      </div>

      {/* Range bar */}
      <RangeBar
        reading={reading}
        unit={unit}
        status={st}
        safe_low={safe_low}
        safe_high={safe_high}
        safe_critical={safe_critical}
        safe_buffer={safe_buffer}
      />

      {/* Plain text descriptions — no overlap possible */}
      <div className="flex flex-col gap-0.5">
        <p className="text-[11px] text-muted leading-snug">{safeRangeLine}</p>
        {criticalLine && (
          <p className="text-[11px] leading-snug" style={{ color: '#EF4444' }}>{criticalLine}</p>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 2c. Live reading section (gauge tiles + status strip)
// ─────────────────────────────────────────────────────────────────────────────
function LiveReadingSection({ device }) {
  const gauges = device.gauges || [];
  const st     = (device.status || 'UNKNOWN').toUpperCase();
  const cfg    = STATUS_CFG[st] || STATUS_CFG.UNKNOWN;
  const isOff  = st === 'OFFLINE';

  return (
    <div className="flex flex-col gap-4">
      {/* Gauge tiles */}
      {gauges.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 gap-3 bg-white rounded-2xl" style={CARD}>
          <AlertTriangle size={28} className="text-amber-400" />
          <p className="text-sm text-muted">No gauges in the latest reading</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {gauges.map((g, i) => <GaugeTile key={`${g.gas}-${g.number}-${i}`} gauge={g} />)}
        </div>
      )}

      {/* Status strip */}
      <div className="bg-white rounded-2xl px-5 py-4 flex flex-wrap gap-5" style={CARD}>
        <InfoPair label="Device status">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold"
            style={{ background: cfg.bg, color: cfg.text }}>
            <span className="w-2 h-2 rounded-full" style={{ background: cfg.dot }} />
            {st}
          </span>
        </InfoPair>
        <InfoPair label="Last updated">
          <span className="text-xs font-semibold text-navy">
            {device.last_seen_at ? timeAgo(device.last_seen_at) : '—'}
          </span>
        </InfoPair>
        <InfoPair label="Connection">
          <span className={`flex items-center gap-1.5 text-xs font-semibold ${isOff ? 'text-muted' : 'text-green-600'}`}>
            {isOff ? <><WifiOff size={13} /> Tablet offline</> : <><Wifi size={13} /> Connected</>}
          </span>
        </InfoPair>
      </div>
    </div>
  );
}

function InfoPair({ label, children }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-[10px] font-bold uppercase tracking-widest text-muted">{label}</p>
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. Reading history chart (per-unit, step)
// ─────────────────────────────────────────────────────────────────────────────
const TIME_OPTS = [
  { label: '15 min', minutes: 15   },
  { label: '1 h',    minutes: 60   },
  { label: '24 h',   minutes: 1440 },
];

const GAS_COLORS = {
  OXYGEN:       '#2F80ED',
  VACUUM:       '#22C55E',
  'MEDICAL AIR':'#F5A524',
  'CO2':        '#F0386B',
  'N2O':        '#8B5CF6',
};
function gasColor(gas) { return GAS_COLORS[(gas || '').toUpperCase()] || '#94A3B8'; }

function HistChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl p-3 text-xs"
      style={{ background: '#fff', border: '1px solid #E8EEFA',
               boxShadow: '0 8px 24px rgba(80,110,180,0.12)', minWidth: 130 }}>
      <p className="mb-2 font-medium text-muted">{label}</p>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 mb-1">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-navy font-semibold">
            {p.value != null ? `${Number(p.value).toFixed(2)} ${p.payload?.unit || ''}` : '—'}
          </span>
        </div>
      ))}
    </div>
  );
}

function GasChart({ deviceId, gas, gaugeData, minutes, wsRev }) {
  const [rows,    setRows]    = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  // Safe thresholds from latest gauge data for this gas
  const refGauge = gaugeData.find(g => (g.gas || '').toUpperCase() === gas.toUpperCase());
  const safeLow  = refGauge?.safe_low  ?? null;
  const safeHigh = refGauge?.safe_high ?? null;
  const unit     = refGauge?.unit      ?? '';

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getReadings(deviceId, gas.toUpperCase(), minutes);
      setRows(
        (data || []).map(r => ({
          time:    fmtTime(r.timestamp),
          value:   r.reading,
          unit:    r.unit || unit,
          status:  r.status,
        }))
      );
    } catch (e) {
      setError(e.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [deviceId, gas, minutes, unit]);

  useEffect(() => { fetch(); }, [fetch, wsRev]);

  const color = gasColor(gas);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
        <p className="text-xs font-semibold text-navy">{gas}</p>
        {unit && <span className="text-[10px] text-muted">({unit})</span>}
      </div>
      {loading ? (
        <Skeleton className="h-36" />
      ) : error ? (
        <div className="flex items-center justify-center h-36 rounded-xl bg-red-50">
          <p className="text-xs text-red-600">{error}</p>
        </div>
      ) : rows.length === 0 ? (
        <div className="flex items-center justify-center h-36 rounded-xl bg-slate-50">
          <p className="text-xs text-muted">No readings in this period</p>
        </div>
      ) : (
        <div style={{ height: 160 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 6, right: 10, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="4 4" stroke="#F0F4FF" vertical={false} />
              <XAxis dataKey="time"
                tick={{ fontSize: 9, fill: '#8A94A6', fontFamily: 'Poppins,sans-serif' }}
                tickLine={false} axisLine={false} interval="preserveStartEnd" />
              <YAxis
                tick={{ fontSize: 9, fill: '#8A94A6', fontFamily: 'Poppins,sans-serif' }}
                tickLine={false} axisLine={false}
                label={{ value: unit, angle: -90, position: 'insideLeft',
                         style: { fontSize: 8, fill: '#8A94A6' }, dx: 14 }} />
              <Tooltip content={<HistChartTooltip />} />
              {safeLow  != null && (
                <ReferenceLine y={safeLow}  stroke="#F59E0B" strokeDasharray="5 3"
                  label={{ value: `Low ${safeLow}`, position: 'insideBottomLeft', fontSize: 9, fill: '#F59E0B' }} />
              )}
              {safeHigh != null && (
                <ReferenceLine y={safeHigh} stroke="#8B5CF6" strokeDasharray="5 3"
                  label={{ value: `High ${safeHigh}`, position: 'insideTopLeft', fontSize: 9, fill: '#8B5CF6' }} />
              )}
              <Line
                type="stepAfter" dataKey="value" name={gas}
                stroke={color} strokeWidth={2}
                dot={false} activeDot={{ r: 4, strokeWidth: 0 }}
                isAnimationActive={false} connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function ReadingHistoryCard({ device, wsRev }) {
  const [minutes, setMinutes] = useState(60);

  // Distinct gas types from latest gauge data
  const gases = useMemo(() => {
    const seen = new Set();
    return (device.gauges || [])
      .filter(g => g.gas && !seen.has(g.gas) && seen.add(g.gas))
      .map(g => g.gas);
  }, [device]);

  return (
    <div className="bg-white rounded-2xl p-5 flex flex-col gap-5" style={CARD}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-sm font-semibold text-navy">Reading History</h2>
          <p className="text-[11px] text-muted mt-0.5">Step chart · separate axes per unit</p>
        </div>
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

      {/* One chart per gas */}
      {gases.length === 0 ? (
        <div className="flex items-center justify-center py-10 text-muted text-sm">
          No gauge data yet
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          {gases.map(gas => (
            <GasChart
              key={gas}
              deviceId={device.device_id}
              gas={gas}
              gaugeData={device.gauges || []}
              minutes={minutes}
              wsRev={wsRev}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. Configure device modal
// ─────────────────────────────────────────────────────────────────────────────
function ConfigureModal({ device, onClose, onSaved, onError }) {
  const [name,     setName]     = useState(device.name     || '');
  const [location, setLocation] = useState(device.location || '');
  const [saving,   setSaving]   = useState(false);

  // Close on Escape
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);

  async function handleSave() {
    setSaving(true);
    try {
      await updateDevice(device.device_id, { name: name.trim() || null, location: location.trim() || null });
      onSaved();
    } catch (e) {
      onError(e.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />
      <div className="relative bg-white rounded-2xl p-6 w-full max-w-md"
        style={{ boxShadow: '0 20px 60px rgba(0,0,0,0.20)' }}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-sm font-bold text-navy">Configure Device</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted hover:bg-slate-100 hover:text-navy">
            <X size={16} />
          </button>
        </div>

        {/* Read-only device info */}
        <div className="bg-slate-50 rounded-xl px-4 py-3 mb-5 flex flex-col gap-1 text-xs">
          <div className="flex justify-between">
            <span className="text-muted">Device ID</span>
            <span className="font-semibold text-navy font-mono">{device.device_id}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">Last message</span>
            <span className="font-semibold text-navy">{device.last_seen_at ? timeAgo(device.last_seen_at) : '—'}</span>
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <div>
            <label className="block text-xs font-semibold text-navy mb-1.5">Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. ICU Oxygen Supply"
              className="w-full px-3 py-2.5 text-sm rounded-xl border border-slate-200 bg-slate-50 outline-none focus:border-blue-400"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-navy mb-1.5">Location</label>
            <input
              type="text"
              value={location}
              onChange={e => setLocation(e.target.value)}
              placeholder="e.g. Ward 3, Room 12"
              className="w-full px-3 py-2.5 text-sm rounded-xl border border-slate-200 bg-slate-50 outline-none focus:border-blue-400"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-muted hover:bg-slate-100 transition-colors">
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-white disabled:opacity-60"
            style={{ background: '#2F80ED' }}>
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. Thresholds panel (read-only, expandable)
// ─────────────────────────────────────────────────────────────────────────────
function ThresholdsPanel({ gauges }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="bg-white rounded-2xl overflow-hidden" style={CARD}>
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-slate-50 transition-colors"
      >
        <span className="text-sm font-semibold text-navy">Thresholds</span>
        {open ? <ChevronUp size={16} className="text-muted" /> : <ChevronDown size={16} className="text-muted" />}
      </button>

      {open && (
        <div className="px-5 pb-5 flex flex-col gap-4">
          <p className="text-xs text-muted flex items-center gap-1.5">
            <Info size={12} /> Thresholds are set on the tablet.
          </p>

          {gauges.length === 0 ? (
            <p className="text-xs text-muted italic">No gauge data.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {gauges.map((g, i) => (
                <div key={i} className="rounded-xl bg-slate-50 px-4 py-3 flex flex-col gap-1.5">
                  <p className="text-xs font-bold text-navy mb-1">
                    {g.gas || 'Unknown'} #{g.number}
                    {g.unit && <span className="ml-1.5 font-normal text-muted">({g.unit})</span>}
                  </p>
                  {[
                    { label: 'Safe critical', value: g.safe_critical, color: '#EF4444' },
                    { label: 'Safe low',      value: g.safe_low,      color: '#F59E0B' },
                    { label: 'Safe high',     value: g.safe_high,     color: '#8B5CF6' },
                  ].map(({ label, value, color }) =>
                    value != null ? (
                      <div key={label} className="flex items-center justify-between text-xs">
                        <span className="text-muted">{label}</span>
                        <span className="font-semibold" style={{ color }}>{value} {g.unit || ''}</span>
                      </div>
                    ) : null
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Disabled edit button */}
          <button
            disabled
            title="Coming soon"
            className="self-start px-4 py-2 rounded-xl text-xs font-semibold text-muted bg-slate-100 cursor-not-allowed opacity-60"
          >
            Edit thresholds
          </button>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 6. Camera feed placeholder
// ─────────────────────────────────────────────────────────────────────────────
function CameraFeedCard() {
  return (
    <div className="bg-white rounded-2xl p-5 flex flex-col gap-4" style={CARD}>
      <div className="flex items-center gap-2">
        <Camera size={16} className="text-muted" />
        <h2 className="text-sm font-semibold text-navy">Camera feed</h2>
      </div>

      {/* Placeholder frame */}
      <div className="rounded-xl bg-slate-100 flex items-center justify-center"
        style={{ height: 140 }}>
        <div className="flex flex-col items-center gap-2">
          <Camera size={28} className="text-slate-300" />
          <p className="text-xs text-muted">Camera data not available yet</p>
        </div>
      </div>

      <div className="flex flex-col gap-1.5 text-xs">
        {[
          { label: 'Camera status',       value: '—' },
          { label: 'Last captured frame', value: '—' },
          { label: 'Detection status',    value: '—' },
        ].map(({ label, value }) => (
          <div key={label} className="flex items-center justify-between">
            <span className="text-muted">{label}</span>
            <span className="font-semibold text-navy">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Toast (local, lightweight — reuses Dashboard styling)
// ─────────────────────────────────────────────────────────────────────────────
function LocalToast({ toast, onDismiss }) {
  if (!toast) return null;
  const cfg = {
    success: { bg: '#F0FDF4', border: '#BBF7D0', text: '#166534', icon: <CheckCircle size={15} className="text-green-500 shrink-0" /> },
    danger:  { bg: '#FEF2F2', border: '#FECACA', text: '#991B1B', icon: <AlertTriangle size={15} className="text-red-500 shrink-0" /> },
  };
  const c = cfg[toast.type] || cfg.danger;
  return (
    <div className="fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-2xl border shadow-xl max-w-sm toast-in"
      style={{ background: c.bg, borderColor: c.border }}>
      {c.icon}
      <p className="text-xs font-semibold flex-1" style={{ color: c.text }}>{toast.message}</p>
      <button onClick={onDismiss} className="text-muted hover:text-navy shrink-0">
        <X size={14} />
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────
export default function LiveMonitoring({ devices = [], loading: devicesLoading }) {
  const { role }  = useAuth();
  const canEdit   = role !== 'VIEWER';

  const [searchParams, setSearchParams] = useSearchParams();
  const [configOpen,   setConfigOpen]   = useState(false);
  const [localToast,   setLocalToast]   = useState(null);

  // ── Device selection ───────────────────────────────────────────────────────
  const deviceParam  = searchParams.get('device');
  const selectedDevice = useMemo(() => {
    if (!devices.length) return null;
    const found = deviceParam ? devices.find(d => d.device_id === deviceParam) : null;
    return found || devices[0];
  }, [devices, deviceParam]);

  function selectDevice(id) {
    setSearchParams({ device: id }, { replace: false });
  }

  // Auto-set URL to first device on initial load
  useEffect(() => {
    if (!deviceParam && devices.length > 0) {
      setSearchParams({ device: devices[0].device_id }, { replace: true });
    }
  }, [devices, deviceParam, setSearchParams]);

  // ── WS revision counter (for child charts) ─────────────────────────────────
  const wsRevRef      = useRef(0);
  const prevDeviceRef = useRef(devices);
  if (devices !== prevDeviceRef.current) {
    wsRevRef.current += 1;
    prevDeviceRef.current = devices;
  }
  const wsRev = wsRevRef.current;

  // ── Toast helpers ──────────────────────────────────────────────────────────
  function showToast(type, message) {
    const id = Date.now();
    setLocalToast({ id, type, message });
    setTimeout(() => setLocalToast(null), 4000);
  }

  // ── Configure handlers ─────────────────────────────────────────────────────
  // After a successful save we need the parent to reload devices.
  // usePortalData.reload() isn't available here, so we trigger a lightweight
  // window event that PortalApp can optionally listen to, or just rely on the
  // next WS message.  For now we show a toast and close the modal; the device
  // list will update on the next reload.
  function handleConfigSaved() {
    setConfigOpen(false);
    showToast('success', 'Device updated. Changes will appear after the next reading.');
  }
  function handleConfigError(msg) {
    setConfigOpen(false);
    showToast('danger', msg);
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  if (devicesLoading) return (
    <div className="p-5 flex flex-col gap-5">
      <Skeleton className="h-14 w-full" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3].map(i => <Skeleton key={i} className="h-56" />)}
      </div>
      <Skeleton className="h-56" />
    </div>
  );

  if (!devices.length) return (
    <div className="p-8 flex flex-col items-center justify-center min-h-[60vh] gap-4">
      <AlertTriangle size={32} className="text-amber-400" />
      <h2 className="text-lg font-bold text-navy">No devices registered</h2>
      <p className="text-sm text-muted max-w-xs text-center">
        No tablets have sent data yet. Send a reading from the tablet or use the mock tool.
      </p>
    </div>
  );

  return (
    <>
      <div className="p-5 flex flex-col gap-5 page-fade-in">
        {/* Title */}
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-lg font-bold text-navy">Live Monitoring</h1>
            <p className="text-xs text-muted mt-0.5">Real-time gauge readings from connected tablets</p>
          </div>
          {canEdit && selectedDevice && (
            <button
              onClick={() => setConfigOpen(true)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold transition-colors hover:bg-slate-100"
              style={{ background: '#F4F7FC', color: '#1E2A4A' }}
            >
              <Settings size={13} /> Configure device
            </button>
          )}
          {!canEdit && selectedDevice && (
            <button
              disabled
              title="Viewer role cannot configure devices"
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold opacity-40 cursor-not-allowed"
              style={{ background: '#F4F7FC', color: '#1E2A4A' }}
            >
              <Settings size={13} /> Configure device
            </button>
          )}
        </div>

        {/* 1. Device selector */}
        <DeviceSelectorRow
          devices={devices}
          selectedId={selectedDevice?.device_id}
          onSelect={selectDevice}
        />

        {selectedDevice && (
          <>
            {/* 2. Live reading section */}
            <LiveReadingSection device={selectedDevice} />

            {/* 3. Reading history */}
            <ReadingHistoryCard device={selectedDevice} wsRev={wsRev} />

            {/* 5. Thresholds + 6. Camera — side by side on wide screens */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
              <ThresholdsPanel gauges={selectedDevice.gauges || []} />
              <CameraFeedCard />
            </div>
          </>
        )}
      </div>

      {/* 4. Configure modal */}
      {configOpen && selectedDevice && (
        <ConfigureModal
          device={selectedDevice}
          onClose={() => setConfigOpen(false)}
          onSaved={handleConfigSaved}
          onError={handleConfigError}
        />
      )}

      {/* Local toast */}
      <LocalToast toast={localToast} onDismiss={() => setLocalToast(null)} />
    </>
  );
}
