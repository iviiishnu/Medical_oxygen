"""
routers/portal.py
=================
Portal-facing REST API — all endpoints require a valid JWT.

GET  /api/summary
GET  /api/devices
PATCH /api/devices/{id}
GET  /api/devices/{id}/readings
GET  /api/alerts
GET  /api/alerts/{id}
POST /api/alerts/{id}/acknowledge
POST /api/alerts/{id}/resolve
GET  /api/activity

Alert resolved status rule (used throughout):
  resolved   if resolved_at OR cleared_at is set
  acknowledged if acknowledged_at is set (and not resolved)
  active     otherwise
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.db.database import get_pool
from app.security import get_current_user, require_write_role
from app.ws_manager import manager

router = APIRouter(prefix="/api", tags=["portal"])

# ── Shared dependencies ───────────────────────────────────────────────────────
_auth       = Depends(get_current_user)
_write_role  = Depends(require_write_role())


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _alert_derived_status(row: dict) -> str:
    """
    Compute the derived alert status from DB timestamps.
    resolved  → resolved_at or cleared_at is set
    acknowledged → acknowledged_at is set
    active    → neither
    """
    if row.get("resolved_at") or row.get("cleared_at"):
        return "resolved"
    if row.get("acknowledged_at"):
        return "acknowledged"
    return "active"


# Severity sort key: lower number = higher priority in listing
_SEVERITY_ORDER = {
    "CRITICAL":    0,
    "HIGH":        1,
    "OFFLINE":     2,
    "UNREADABLE":  2,
    "MEDIUM":      3,
    "LOW":         4,
}


def _severity_key(severity: str | None) -> int:
    return _SEVERITY_ORDER.get(severity or "", 99)


# ── Alert-type to priority bucket (for ordering within same derived status) ──
_TYPE_PRIORITY = {
    "PANEL_CRITICAL": 0,
    "UNREADABLE":     1,
    "TABLET_OFFLINE": 1,
}


def _normalize_reasons(raw) -> list:
    """
    Always return reasons as a Python list of strings.

    asyncpg returns a JSONB column as a already-decoded Python object
    (list or str).  If it was double-encoded (json.dumps of a list stored
    as jsonb), PostgreSQL stores it as a JSON string scalar and asyncpg
    hands us back a str.  Parse that string once and ensure we have a list.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else [parsed]
        except (json.JSONDecodeError, TypeError):
            return [raw]
    return []


async def _log_activity(
    conn,
    event_type: str,
    device_id: str | None,
    alert_id: int | None,
    actor: str,
    detail: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO activity_log (event_type, device_id, alert_id, actor, detail)
        VALUES ($1, $2, $3, $4, $5)
        """,
        event_type, device_id, alert_id, actor, detail,
    )


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/summary
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/summary")
async def get_summary(user: dict = _auth):
    pool = get_pool()
    async with pool.acquire() as conn:
        # Device counts
        device_rows = await conn.fetch(
            "SELECT status FROM tablet_devices"
        )
        total_devices    = len(device_rows)
        normal_devices   = sum(1 for r in device_rows if r["status"] == "NORMAL")
        critical_devices = sum(1 for r in device_rows if r["status"] == "CRITICAL")
        offline_devices  = sum(1 for r in device_rows if r["status"] == "OFFLINE")

        # Alert counts using derived status rule
        alert_rows = await conn.fetch(
            "SELECT acknowledged_at, resolved_at, cleared_at FROM tablet_alerts"
        )
        total_alerts        = len(alert_rows)
        active_alerts       = sum(1 for r in alert_rows
                                  if _alert_derived_status(dict(r)) == "active")
        acknowledged_alerts = sum(1 for r in alert_rows
                                  if _alert_derived_status(dict(r)) == "acknowledged")
        resolved_alerts     = sum(1 for r in alert_rows
                                  if _alert_derived_status(dict(r)) == "resolved")

    return {
        "devices": {
            "total":    total_devices,
            "normal":   normal_devices,
            "critical": critical_devices,
            "offline":  offline_devices,
        },
        "alerts": {
            "total":        total_alerts,
            "active":       active_alerts,
            "acknowledged": acknowledged_alerts,
            "resolved":     resolved_alerts,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/devices
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/devices")
async def list_devices(user: dict = _auth):
    pool = get_pool()
    async with pool.acquire() as conn:
        devices = await conn.fetch(
            """
            SELECT device_id, name, location, status, last_seen_at
            FROM   tablet_devices
            ORDER  BY device_id
            """
        )

        result = []
        for dev in devices:
            device_id = dev["device_id"]

            # Latest gauges: one row per (gas, number) from the most recent message
            latest_msg_id = await conn.fetchval(
                """
                SELECT id FROM tablet_messages
                WHERE  device_id = $1
                ORDER  BY timestamp DESC
                LIMIT  1
                """,
                device_id,
            )

            gauges = []
            if latest_msg_id:
                gauge_rows = await conn.fetch(
                    """
                    SELECT gas, number, reading, unit, status,
                           safe_low, safe_high, safe_critical
                    FROM   gauge_readings
                    WHERE  message_id = $1
                      AND  UPPER(gas)  != 'VACUUM'
                      AND  LOWER(unit) != 'mmhg'
                    ORDER  BY number
                    """,
                    latest_msg_id,
                )
                for g in gauge_rows:
                    gauges.append({
                        "gas":           g["gas"],
                        "number":        g["number"],
                        "reading":       float(g["reading"]) if g["reading"] is not None else None,
                        "unit":          g["unit"],
                        "status":        g["status"],
                        "safe_low":      float(g["safe_low"])      if g["safe_low"]      is not None else None,
                        "safe_high":     float(g["safe_high"])     if g["safe_high"]     is not None else None,
                        "safe_critical": float(g["safe_critical"]) if g["safe_critical"] is not None else None,
                    })

            result.append({
                "device_id":    device_id,
                "name":         dev["name"],
                "location":     dev["location"],
                "status":       dev["status"],
                "last_seen_at": dev["last_seen_at"],
                "gauges":       gauges,
            })

    return result


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /api/devices/{id}
# ══════════════════════════════════════════════════════════════════════════════

class DevicePatch(BaseModel):
    name:     Optional[str] = None
    location: Optional[str] = None


@router.patch("/devices/{device_id}")
async def patch_device(device_id: str, body: DevicePatch, user: dict = _write_role):
    if body.name is None and body.location is None:
        raise HTTPException(status_code=400, detail="Provide at least one of: name, location")

    pool = get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM tablet_devices WHERE device_id = $1", device_id
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Device not found")

        if body.name is not None:
            await conn.execute(
                "UPDATE tablet_devices SET name = $1 WHERE device_id = $2",
                body.name, device_id,
            )
        if body.location is not None:
            await conn.execute(
                "UPDATE tablet_devices SET location = $1 WHERE device_id = $2",
                body.location, device_id,
            )

        row = await conn.fetchrow(
            "SELECT device_id, name, location, status, last_seen_at FROM tablet_devices WHERE device_id = $1",
            device_id,
        )

    return dict(row)


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/devices/{id}/readings
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/devices/{device_id}/readings")
async def get_device_readings(
    device_id: str,
    gas:     Optional[str] = Query(None, description="Filter by gas, e.g. OXYGEN"),
    minutes: int           = Query(60, ge=1, le=10080, description="Time window in minutes"),
    user: dict = _auth,
):
    pool = get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM tablet_devices WHERE device_id = $1", device_id
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Device not found")

        if gas:
            rows = await conn.fetch(
                """
                SELECT gr.timestamp, gr.reading, gr.status, gr.unit, gr.gas, gr.number
                FROM   gauge_readings gr
                WHERE  gr.device_id = $1
                  AND  gr.gas       = $2
                  AND  gr.timestamp >= NOW() - ($3 * INTERVAL '1 minute')
                ORDER  BY gr.timestamp ASC
                """,
                device_id, gas.upper(), minutes,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT gr.timestamp, gr.reading, gr.status, gr.unit, gr.gas, gr.number
                FROM   gauge_readings gr
                WHERE  gr.device_id = $1
                  AND  gr.timestamp >= NOW() - ($2 * INTERVAL '1 minute')
                ORDER  BY gr.timestamp ASC
                """,
                device_id, minutes,
            )

    return [
        {
            "timestamp": r["timestamp"],
            "reading":   float(r["reading"]) if r["reading"] is not None else None,
            "status":    r["status"],
            "unit":      r["unit"],
            "gas":       r["gas"],
            "number":    r["number"],
        }
        for r in rows
    ]


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/alerts
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/alerts")
async def list_alerts(
    status_filter: str = Query("active", alias="status",
                               description="active | acknowledged | resolved | all"),
    user: dict = _auth,
):
    valid = {"active", "acknowledged", "resolved", "all"}
    if status_filter not in valid:
        raise HTTPException(status_code=400, detail=f"status must be one of {valid}")

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, device_id, alert_type, severity,
                   started_at, cleared_at,
                   worst_status, reasons, confidence_pct,
                   acknowledged_at, acknowledged_by,
                   resolved_at, resolved_by, resolution_note
            FROM   tablet_alerts
            ORDER  BY started_at DESC
            """
        )

    result = []
    for r in rows:
        d = dict(r)
        derived = _alert_derived_status(d)
        if status_filter != "all" and derived != status_filter:
            continue
        d["status"]  = derived
        d["reasons"] = _normalize_reasons(d.get("reasons"))
        result.append(d)

    # Sort order:
    #   1. derived status: active → acknowledged → resolved
    #   2. severity within that group: CRITICAL > LOW/HIGH > OFFLINE/UNREADABLE > NEAR
    #   3. within active/acknowledged: oldest started_at first (longest-waiting)
    #      within resolved: newest started_at first
    _STATUS_ORDER = {"active": 0, "acknowledged": 1, "resolved": 2}

    def _sort_key(row):
        derived  = row["status"]
        status_k = _STATUS_ORDER.get(derived, 99)
        sev_k    = _severity_key(row.get("severity"))
        type_k   = _TYPE_PRIORITY.get(row.get("alert_type", ""), 99)
        ts = row.get("started_at") or datetime.max.replace(tzinfo=timezone.utc)
        # resolved group: newest first → negate timestamp for sort
        if derived == "resolved":
            ts_key = -ts.timestamp()
        else:
            ts_key = ts.timestamp()
        return (status_k, sev_k, type_k, ts_key)

    result.sort(key=_sort_key)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/alerts/{id}
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: int, user: dict = _auth):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, device_id, alert_type, severity,
                   started_at, cleared_at, worst_status, reasons,
                   confidence_pct, start_message_id,
                   acknowledged_at, acknowledged_by, acknowledge_note,
                   resolved_at, resolved_by, resolution_note
            FROM   tablet_alerts
            WHERE  id = $1
            """,
            alert_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Alert not found")

        alert = dict(row)
        alert["status"]  = _alert_derived_status(alert)
        alert["reasons"] = _normalize_reasons(alert.get("reasons"))

        # Linked incident (if any)
        inc_row = await conn.fetchrow(
            "SELECT id FROM incidents WHERE alert_id = $1 LIMIT 1",
            alert_id,
        )
        alert["incident_id"] = inc_row["id"] if inc_row else None

        # Last 10 gauge readings before the alert started
        pre_readings = await conn.fetch(
            """
            SELECT gr.timestamp, gr.gas, gr.number, gr.reading,
                   gr.unit, gr.status
            FROM   gauge_readings gr
            WHERE  gr.device_id = $1
              AND  gr.timestamp < $2
            ORDER  BY gr.timestamp DESC
            LIMIT  10
            """,
            alert["device_id"],
            alert["started_at"],
        )
        alert["pre_readings"] = [dict(r) for r in reversed(pre_readings)]

    return alert


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/alerts/{id}/acknowledge
# ══════════════════════════════════════════════════════════════════════════════

class NoteBody(BaseModel):
    note: Optional[str] = None


@router.post("/alerts/{alert_id}/acknowledge", status_code=200)
async def acknowledge_alert(alert_id: int, body: NoteBody, user: dict = _write_role):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, device_id, acknowledged_at, cleared_at, resolved_at FROM tablet_alerts WHERE id = $1",
            alert_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Alert not found")

        # Already resolved?
        if row["resolved_at"] or row["cleared_at"]:
            raise HTTPException(status_code=409, detail="Alert is already resolved")

        if row["acknowledged_at"]:
            raise HTTPException(status_code=409, detail="Alert is already acknowledged")

        now = datetime.now(timezone.utc)
        await conn.execute(
            """
            UPDATE tablet_alerts
            SET    acknowledged_at   = $1,
                   acknowledged_by   = $2,
                   acknowledge_note  = $3
            WHERE  id = $4
            """,
            now,
            user["username"],
            body.note,
            alert_id,
        )
        await _log_activity(
            conn, "alert_acknowledged", row["device_id"], alert_id,
            user["username"],
            body.note or "",
        )

    await manager.broadcast({"type": "alert", "device_id": row["device_id"]})
    return {"status": "acknowledged"}


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/alerts/{id}/resolve
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/alerts/{alert_id}/resolve", status_code=200)
async def resolve_alert(alert_id: int, body: NoteBody, user: dict = _write_role):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, device_id, resolved_at, cleared_at FROM tablet_alerts WHERE id = $1",
            alert_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Alert not found")

        if row["resolved_at"] or row["cleared_at"]:
            raise HTTPException(status_code=409, detail="Alert is already resolved")

        now = datetime.now(timezone.utc)
        await conn.execute(
            """
            UPDATE tablet_alerts
            SET    resolved_at      = $1,
                   resolved_by      = $2,
                   resolution_note  = $3
            WHERE  id = $4
            """,
            now,
            user["username"],
            body.note,
            alert_id,
        )
        await _log_activity(
            conn, "alert_resolved", row["device_id"], alert_id,
            user["username"],
            body.note or "",
        )

    await manager.broadcast({"type": "alert", "device_id": row["device_id"]})
    return {"status": "resolved"}


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/activity
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/activity")
async def get_activity(user: dict = _auth):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, event_type, device_id, alert_id, actor, detail, created_at
            FROM   activity_log
            ORDER  BY created_at DESC
            LIMIT  15
            """
        )
    return [dict(r) for r in rows]
