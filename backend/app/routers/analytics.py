"""
routers/analytics.py
=====================
Analytics & Reports API — all endpoints require a valid JWT.

GET /api/analytics?from=<ISO>&to=<ISO>
    Aggregated stats for the window: alerts, devices (uptime), incidents,
    and per-device oxygen pressure trend (Oxygen / Medical Air, kg/cm2 only).

GET /api/export/alerts.csv    ?from&to
GET /api/export/incidents.csv ?from&to
GET /api/export/readings.csv  ?from&to
    CSV downloads (Content-Disposition set).

Uptime rule: share of the window where the gap between consecutive messages
is <= 90 s.  A longer gap counts as offline for the excess (gap - 90 s),
measured on the message timestamp, not arrival time.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.db.database import get_pool
from app.security import get_current_user

router = APIRouter(prefix="/api", tags=["analytics"])

_auth = Depends(get_current_user)

OFFLINE_GAP_S = 90          # seconds — a gap longer than this is offline
TREND_MAX_POINTS = 300       # downsample limit per device


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_bounds(
    from_raw: Optional[str], to_raw: Optional[str]
) -> tuple[datetime, datetime]:
    to_dt = _parse_iso(to_raw) or datetime.now(timezone.utc)
    from_dt = _parse_iso(from_raw) or (to_dt - timedelta(days=7))
    if from_dt >= to_dt:
        from_dt = to_dt - timedelta(days=1)
    return from_dt, to_dt


def _parse_iso(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _avg_seconds(rows, start_col: str, end_col: str) -> Optional[float]:
    """Average (end - start) in seconds across rows where both are set."""
    deltas = []
    for r in rows:
        s, e = r[start_col], r[end_col]
        if s and e and e > s:
            deltas.append((e - s).total_seconds())
    return round(sum(deltas) / len(deltas), 1) if deltas else None


def _bucket_alert_type(t: str | None) -> str:
    if t in ("PANEL_CRITICAL", "TABLET_OFFLINE", "UNREADABLE"):
        return t
    return "OTHER"


# ── CSV helper ───────────────────────────────────────────────────────────────

def _csv_response(rows: list[dict], columns: list[str], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/analytics
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/analytics")
async def get_analytics(
    from_raw: Optional[str] = Query(None, alias="from"),
    to_raw:   Optional[str] = Query(None, alias="to"),
    user: dict = _auth,
):
    from_dt, to_dt = _parse_bounds(from_raw, to_raw)

    pool = get_pool()
    async with pool.acquire() as conn:
        # ── Alerts ────────────────────────────────────────────────────────
        alert_rows = await conn.fetch(
            """
            SELECT id, device_id, alert_type, severity, started_at,
                   acknowledged_at, resolved_at, cleared_at
            FROM   tablet_alerts
            WHERE  started_at >= $1 AND started_at < $2
            """,
            from_dt, to_dt,
        )

        by_type: dict[str, int] = {}
        by_device: dict[str, int] = {}
        per_day: dict[tuple[str, str], int] = {}
        for r in alert_rows:
            bt = _bucket_alert_type(r["alert_type"])
            by_type[bt] = by_type.get(bt, 0) + 1
            if r["device_id"]:
                by_device[r["device_id"]] = by_device.get(r["device_id"], 0) + 1
                day = r["started_at"].astimezone(timezone.utc).date().isoformat()
                per_day[(day, r["device_id"])] = per_day.get((day, r["device_id"]), 0) + 1

        alerts = {
            "total": len(alert_rows),
            "by_type": [{"type": k, "count": v} for k, v in sorted(by_type.items(), key=lambda kv: -kv[1])],
            "per_day": [
                {"date": d, "device_id": dev, "count": c}
                for (d, dev), c in sorted(per_day.items())
            ],
            "by_device": [
                {"device_id": dev, "count": c}
                for dev, c in sorted(by_device.items(), key=lambda kv: -kv[1])
            ],
            "avg_ack_seconds":     _avg_seconds(alert_rows, "started_at", "acknowledged_at"),
            "avg_resolve_seconds": _avg_seconds(alert_rows, "started_at", "resolved_at")
                                   or _avg_seconds(alert_rows, "started_at", "cleared_at"),
        }

        # ── Devices (uptime) ───────────────────────────────────────────────
        device_rows = await conn.fetch(
            "SELECT device_id, name FROM tablet_devices ORDER BY device_id"
        )

        devices = []
        for dev in device_rows:
            did = dev["device_id"]
            # message timestamps inside the window (for uptime)
            ts_rows = await conn.fetch(
                """
                SELECT timestamp FROM tablet_messages
                WHERE  device_id = $1 AND timestamp >= $2 AND timestamp < $3
                ORDER  BY timestamp ASC
                """,
                did, from_dt, to_dt,
            )
            # non-vacuum, kg/cm2 gauge reading count (Oxygen / Medical Air)
            readings_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM gauge_readings
                WHERE  device_id = $1
                  AND  timestamp >= $2 AND timestamp < $3
                  AND  UPPER(gas)  != 'VACUUM'
                  AND  LOWER(unit) = 'kg/cm2'
                """,
                did, from_dt, to_dt,
            )
            last_message_at = await conn.fetchval(
                "SELECT MAX(timestamp) FROM tablet_messages WHERE device_id = $1",
                did,
            )

            window_s = (to_dt - from_dt).total_seconds()
            offline_s = 0.0
            stamps = [r["timestamp"] for r in ts_rows]
            if stamps:
                # leading edge: window start → first message
                offline_s += max(0.0, (stamps[0] - from_dt).total_seconds() - OFFLINE_GAP_S)
                # gaps between consecutive messages
                for a, b in zip(stamps, stamps[1:]):
                    gap = (b - a).total_seconds()
                    if gap > OFFLINE_GAP_S:
                        offline_s += gap - OFFLINE_GAP_S
                # trailing edge: last message → window end
                offline_s += max(0.0, (to_dt - stamps[-1]).total_seconds() - OFFLINE_GAP_S)
            else:
                # no messages at all in the window
                offline_s += max(0.0, window_s - OFFLINE_GAP_S) if last_message_at else window_s

            monitored_s = window_s
            uptime = round(100.0 * max(0.0, monitored_s - offline_s) / monitored_s, 2) if monitored_s > 0 else 100.0

            devices.append({
                "device_id":        did,
                "name":             dev["name"],
                "readings_count":   readings_count,
                "last_message_at":  last_message_at,
                "uptime_pct":       uptime,
                "offline_seconds":  round(offline_s, 1),
                "monitored_seconds": round(monitored_s, 1),
            })

        # ── Incidents ──────────────────────────────────────────────────────
        inc_rows = await conn.fetch(
            """
            SELECT id, device_id, status, created_at, closed_at
            FROM   incidents
            WHERE  created_at >= $1 AND created_at < $2
            """,
            from_dt, to_dt,
        )
        inc_by_device: dict[str, int] = {}
        for r in inc_rows:
            if r["device_id"]:
                inc_by_device[r["device_id"]] = inc_by_device.get(r["device_id"], 0) + 1
        incidents = {
            "total":       len(inc_rows),
            "open":        sum(1 for r in inc_rows if r["status"] == "open"),
            "in_progress": sum(1 for r in inc_rows if r["status"] == "in_progress"),
            "closed":      sum(1 for r in inc_rows if r["status"] == "closed"),
            "by_device": [
                {"device_id": dev, "count": c}
                for dev, c in sorted(inc_by_device.items(), key=lambda kv: -kv[1])
            ],
            "avg_resolve_seconds": _avg_seconds(inc_rows, "created_at", "closed_at"),
        }

        # ── Trend (Oxygen / Medical Air, kg/cm2, per device) ────────────────
        trend = []
        for dev in device_rows:
            did = dev["device_id"]
            rows = await conn.fetch(
                """
                SELECT gr.timestamp, gr.reading, gr.safe_low, gr.safe_high, gr.gas, gr.number
                FROM   gauge_readings gr
                WHERE  gr.device_id = $1
                  AND  gr.timestamp >= $2 AND gr.timestamp < $3
                  AND  UPPER(gr.gas)  != 'VACUUM'
                  AND  LOWER(gr.unit) = 'kg/cm2'
                ORDER  BY gr.timestamp ASC
                """,
                did, from_dt, to_dt,
            )
            if not rows:
                continue

            # Prefer the OXYGEN gauge (lowest number); fall back to any
            oxy = [r for r in rows if (r["gas"] or "").upper() == "OXYGEN"]
            series = oxy or rows
            if oxy:
                min_num = min(r["number"] or 1 for r in oxy)
                series = [r for r in oxy if (r["number"] or 1) == min_num] or oxy

            # Downsample to at most TREND_MAX_POINTS
            stride = max(1, len(series) // TREND_MAX_POINTS)
            sampled = series[::stride]
            if series and sampled[-1] is not series[-1]:
                sampled.append(series[-1])

            vals = [float(r["reading"]) for r in series if r["reading"] is not None]
            last = series[-1]
            trend.append({
                "device_id": did,
                "gas":       (oxy[0]["gas"] if oxy else rows[0]["gas"]),
                "points": [
                    {"t": r["timestamp"].isoformat(), "v": float(r["reading"]) if r["reading"] is not None else None}
                    for r in sampled
                ],
                "avg":       round(sum(vals) / len(vals), 3) if vals else None,
                "min":       min(vals) if vals else None,
                "max":       max(vals) if vals else None,
                "safe_low":  float(last["safe_low"])  if last["safe_low"]  is not None else None,
                "safe_high": float(last["safe_high"]) if last["safe_high"] is not None else None,
            })

    return {
        "from": from_dt.isoformat(),
        "to":   to_dt.isoformat(),
        "alerts":    alerts,
        "devices":   devices,
        "incidents": incidents,
        "trend":     trend,
    }


# ══════════════════════════════════════════════════════════════════════════════
# CSV exports
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/export/alerts.csv")
async def export_alerts(
    from_raw: Optional[str] = Query(None, alias="from"),
    to_raw:   Optional[str] = Query(None, alias="to"),
    user: dict = _auth,
):
    from_dt, to_dt = _parse_bounds(from_raw, to_raw)
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, device_id, alert_type, severity, worst_status,
                   started_at, cleared_at, acknowledged_at, acknowledged_by,
                   resolved_at, resolved_by, resolution_note, confidence_pct
            FROM   tablet_alerts
            WHERE  started_at >= $1 AND started_at < $2
            ORDER  BY started_at DESC
            """,
            from_dt, to_dt,
        )
    cols = ["id", "device_id", "alert_type", "severity", "worst_status",
            "started_at", "cleared_at", "acknowledged_at", "acknowledged_by",
            "resolved_at", "resolved_by", "resolution_note", "confidence_pct"]
    return _csv_response([dict(r) for r in rows], cols, "alerts.csv")


@router.get("/export/incidents.csv")
async def export_incidents(
    from_raw: Optional[str] = Query(None, alias="from"),
    to_raw:   Optional[str] = Query(None, alias="to"),
    user: dict = _auth,
):
    from_dt, to_dt = _parse_bounds(from_raw, to_raw)
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, alert_id, device_id, title, description, possible_cause,
                   severity, assigned_to, status, resolution, created_by,
                   created_at, updated_at, closed_at
            FROM   incidents
            WHERE  created_at >= $1 AND created_at < $2
            ORDER  BY created_at DESC
            """,
            from_dt, to_dt,
        )
    cols = ["id", "alert_id", "device_id", "title", "description", "possible_cause",
            "severity", "assigned_to", "status", "resolution", "created_by",
            "created_at", "updated_at", "closed_at"]
    return _csv_response([dict(r) for r in rows], cols, "incidents.csv")


@router.get("/export/readings.csv")
async def export_readings(
    from_raw: Optional[str] = Query(None, alias="from"),
    to_raw:   Optional[str] = Query(None, alias="to"),
    user: dict = _auth,
):
    from_dt, to_dt = _parse_bounds(from_raw, to_raw)
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT gr.device_id, gr.gas, gr.number, gr.reading, gr.unit,
                   gr.status, gr.status_text, gr.confidence_pct, gr.timestamp
            FROM   gauge_readings gr
            WHERE  gr.timestamp >= $1 AND gr.timestamp < $2
              AND  UPPER(gr.gas)  != 'VACUUM'
              AND  LOWER(gr.unit) = 'kg/cm2'
            ORDER  BY gr.device_id, gr.timestamp ASC
            """,
            from_dt, to_dt,
        )
    cols = ["device_id", "gas", "number", "reading", "unit",
            "status", "status_text", "confidence_pct", "timestamp"]
    return _csv_response([dict(r) for r in rows], cols, "readings.csv")
