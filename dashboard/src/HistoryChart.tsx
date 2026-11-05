import { useMemo, useRef, useState } from 'react';
import { decimate, niceTicks, segments, type Point } from './logic.ts';

interface Props {
  points: Point[];
  low: number;
  critical: number;
  unit: string;
  nowMs: number;
}

const W = 900, H = 280, M = { l: 44, r: 92, t: 12, b: 28 };
const SPAN = 24 * 3600_000;

/** 24-hour pressure line: one series, dashed LOW / CRITICAL reference lines, crosshair tooltip. */
export function HistoryChart({ points, low, critical, unit, nowMs }: Props) {
  const [hover, setHover] = useState<Point | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const t0 = nowMs - SPAN;
  const data = useMemo(() => decimate(points.filter(p => p.t >= t0), 600), [points, t0]);
  const vals = data.filter(p => p.v != null).map(p => p.v as number);
  const vMax = Math.max(low + 1, ...vals, 0) * 1.08;
  const yTicks = niceTicks(0, vMax, 5);
  const yTop = yTicks[yTicks.length - 1] >= vMax ? yTicks[yTicks.length - 1] : vMax;
  const x = (t: number) => M.l + ((t - t0) / SPAN) * (W - M.l - M.r);
  const y = (v: number) => M.t + (1 - v / yTop) * (H - M.t - M.b);
  const segs = segments(data, 3 * 60_000);
  const hours = Array.from({ length: 7 }, (_, i) => t0 + i * 4 * 3600_000);

  function onMove(e: React.PointerEvent) {
    const svg = svgRef.current;
    if (!svg || !data.length) return;
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const t = t0 + ((px - M.l) / (W - M.l - M.r)) * SPAN;
    let best = data[0];
    for (const p of data) if (Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
    setHover(best);
  }

  const fmt = (t: number) => new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  return (
    <div className="chart-wrap">
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="chart" role="img"
        aria-label={`Pressure over the last 24 hours, ${unit}`}
        onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        {yTicks.map(v => (
          <g key={v}>
            <line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} className="gridline" />
            <text x={M.l - 8} y={y(v) + 4} className="tick" textAnchor="end">{v}</text>
          </g>
        ))}
        {hours.map(t => (
          <text key={t} x={x(t)} y={H - 8} className="tick" textAnchor="middle">{fmt(t)}</text>
        ))}
        <line x1={M.l} x2={W - M.r} y1={y(0)} y2={y(0)} className="axis" />
        {[{ v: low, cls: 'ref-low', name: 'LOW' }, { v: critical, cls: 'ref-crit', name: 'CRITICAL' }].map(r => (
          <g key={r.name}>
            <line x1={M.l} x2={W - M.r} y1={y(r.v)} y2={y(r.v)} className={`ref ${r.cls}`} />
            <text x={W - M.r + 6} y={y(r.v) + 4} className="ref-label">{r.name} {r.v}</text>
          </g>
        ))}
        {segs.map((s, i) => (
          <polyline key={i} className="series" points={s.map(p => `${x(p.t)},${y(p.v as number)}`).join(' ')} />
        ))}
        {hover && hover.v != null && (
          <g pointerEvents="none">
            <line x1={x(hover.t)} x2={x(hover.t)} y1={M.t} y2={H - M.b} className="crosshair" />
            <circle cx={x(hover.t)} cy={y(hover.v)} r={5} className="dot" />
          </g>
        )}
      </svg>
      {hover && (
        <div className="tooltip" style={{ left: `${(x(hover.t) / W) * 100}%` }}>
          <div className="tt-time">{new Date(hover.t).toLocaleString()}</div>
          <div className="tt-val">{hover.v == null ? 'no reading' : `${hover.v.toFixed(2)} ${unit}`}</div>
          <div className="tt-sub">{hover.status}</div>
        </div>
      )}
      {!vals.length && <div className="empty">No readings in the last 24 hours</div>}
    </div>
  );
}
