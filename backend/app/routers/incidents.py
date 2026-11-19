"""
routers/incidents.py
====================
Incident management API — all endpoints require a valid JWT.

GET  /api/incidents?status=open|in_progress|closed|all
GET  /api/incidents/{id}        — includes notes + linked alert info
POST /api/incidents             — create
PATCH /api/incidents/{id}       — update status, assigned_to, resolution
POST /api/incidents/{id}/notes  — add a note

Viewer role (role == 'VIEWER') gets 403 on all write operations.
Alert open/close logic is NOT touched.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.db.database import get_pool
from app.security import get_current_user

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

_auth = Depends(get_current_user)

VALID_STATUSES = {"open", "in_progress", "closed"}


# ── Schema migration (called once from init_db / on first request) ────────────
# We use idempotent DDL so it is safe to run on every startup.
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS incidents (
    id             SERIAL       PRIMARY KEY,
    alert_id       INTEGER,                          -- nullable FK to tablet_alerts
    device_id      VARCHAR(50),
    title          VARCHAR(200) NOT NULL,
    description    TEXT,
    possible_cause TEXT,
    severity       VARCHAR(20)  NOT NULL DEFAULT 'Warning'
                       CHECK (severity IN ('Critical','Warning')),
    assigned_to    VARCHAR(100),
    status         VARCHAR(20)  NOT NULL DEFAULT 'open'
                       CHECK (status IN ('open','in_progress','closed')),
    resolution     TEXT,
    created_by     VARCHAR(100) NOT NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    closed_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_incidents_status
    ON incidents (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_incidents_alert
    ON incidents (alert_id)
    WHERE alert_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS incident_notes (
    id          SERIAL       PRIMARY KEY,
    incident_id INTEGER      NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    note        TEXT         NOT NULL,
    author      VARCHAR(100) NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incident_notes_incident
    ON incident_notes (incident_id, created_at ASC);
"""


async def ensure_schema() -> None:
    """Run idempotent DDL — called once at startup from init_db extension."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_write(user: dict) -> None:
    if user.get("role") == "VIEWER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewer role cannot modify incidents",
        )


async def _log_activity(conn, event_type: str, device_id, alert_id, actor: str, detail: str) -> None:
    await conn.execute(
        """
        INSERT INTO activity_log (event_type, device_id, alert_id, actor, detail)
        VALUES ($1, $2, $3, $4, $5)
        """,
        event_type, device_id, alert_id, actor, detail,
    )


async def _fetch_incident(conn, incident_id: int) -> dict | None:
    row = await conn.fetchrow(
        """
        SELECT id, alert_id, device_id, title, description, possible_cause,
               severity, assigned_to, status, resolution,
               created_by, created_at, updated_at, closed_at
        FROM   incidents
        WHERE  id = $1
        """,
        incident_id,
    )
    return dict(row) if row else None


async def _fetch_notes(conn, incident_id: int) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, incident_id, note, author, created_at
        FROM   incident_notes
        WHERE  incident_id = $1
        ORDER  BY created_at ASC
        """,
        incident_id,
    )
    return [dict(r) for r in rows]


async def _fetch_linked_alert(conn, alert_id: int) -> dict | None:
    """Return a lightweight summary of the linked tablet alert."""
    row = await conn.fetchrow(
        """
        SELECT ta.id, ta.device_id, ta.alert_type, ta.severity,
               ta.started_at, ta.cleared_at, ta.worst_status,
               ta.reasons, ta.confidence_pct,
               gr.reading, gr.unit
        FROM   tablet_alerts ta
        LEFT   JOIN LATERAL (
            SELECT reading, unit
            FROM   gauge_readings
            WHERE  device_id = ta.device_id
              AND  timestamp <= ta.started_at
              AND  UPPER(gas)  != 'VACUUM'
              AND  LOWER(unit) != 'mmhg'
            ORDER  BY timestamp DESC
            LIMIT  1
        ) gr ON TRUE
        WHERE  ta.id = $1
        """,
        alert_id,
    )
    if not row:
        return None
    d = dict(row)
    # Normalise reasons
    raw = d.get("reasons")
    if raw is None:
        d["reasons"] = []
    elif isinstance(raw, list):
        pass
    elif isinstance(raw, str):
        import json
        try:
            parsed = json.loads(raw)
            d["reasons"] = parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            d["reasons"] = [raw]
    # Derived status
    if d.get("cleared_at"):
        d["status"] = "resolved"
    else:
        d["status"] = "active"
    return d


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/incidents
# ══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_incidents(
    status_filter: str = Query("open", alias="status",
                               description="open | in_progress | closed | all"),
    user: dict = _auth,
):
    if status_filter not in {"open", "in_progress", "closed", "all"}:
        raise HTTPException(400, "status must be one of: open, in_progress, closed, all")

    pool = get_pool()
    async with pool.acquire() as conn:
        if status_filter == "all":
            rows = await conn.fetch(
                """
                SELECT id, alert_id, device_id, title, description, possible_cause,
                       severity, assigned_to, status, resolution,
                       created_by, created_at, updated_at, closed_at
                FROM   incidents
                ORDER  BY created_at DESC
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, alert_id, device_id, title, description, possible_cause,
                       severity, assigned_to, status, resolution,
                       created_by, created_at, updated_at, closed_at
                FROM   incidents
                WHERE  status = $1
                ORDER  BY created_at DESC
                """,
                status_filter,
            )
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/incidents/{id}
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{incident_id}")
async def get_incident(incident_id: int, user: dict = _auth):
    pool = get_pool()
    async with pool.acquire() as conn:
        inc = await _fetch_incident(conn, incident_id)
        if not inc:
            raise HTTPException(404, "Incident not found")

        notes = await _fetch_notes(conn, incident_id)
        inc["notes"] = notes

        # Linked alert info (if any)
        if inc.get("alert_id"):
            inc["linked_alert"] = await _fetch_linked_alert(conn, inc["alert_id"])
        else:
            inc["linked_alert"] = None

    return inc


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/incidents
# ══════════════════════════════════════════════════════════════════════════════

class IncidentCreate(BaseModel):
    title:          str           = Field(..., min_length=1, max_length=200)
    device_id:      Optional[str] = None
    alert_id:       Optional[int] = None
    description:    Optional[str] = None
    possible_cause: Optional[str] = None
    severity:       str           = "Warning"
    assigned_to:    Optional[str] = None


@router.post("", status_code=201)
async def create_incident(body: IncidentCreate, user: dict = _auth):
    _require_write(user)

    if body.severity not in ("Critical", "Warning"):
        raise HTTPException(400, "severity must be Critical or Warning")

    pool = get_pool()
    async with pool.acquire() as conn:
        # Validate alert_id if provided
        if body.alert_id is not None:
            exists = await conn.fetchval(
                "SELECT 1 FROM tablet_alerts WHERE id = $1", body.alert_id
            )
            if not exists:
                raise HTTPException(404, f"Alert {body.alert_id} not found")

        incident_id = await conn.fetchval(
            """
            INSERT INTO incidents
                (alert_id, device_id, title, description, possible_cause,
                 severity, assigned_to, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            RETURNING id
            """,
            body.alert_id,
            body.device_id,
            body.title,
            body.description,
            body.possible_cause,
            body.severity,
            body.assigned_to,
            user["username"],
        )

        await _log_activity(
            conn, "incident_created",
            body.device_id, body.alert_id,
            user["username"],
            f"Incident #{incident_id}: {body.title}",
        )

        return await _fetch_incident(conn, incident_id)


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /api/incidents/{id}
# ══════════════════════════════════════════════════════════════════════════════

class IncidentPatch(BaseModel):
    status:      Optional[str] = None
    assigned_to: Optional[str] = None
    resolution:  Optional[str] = None
    title:       Optional[str] = None
    description: Optional[str] = None


@router.patch("/{incident_id}")
async def patch_incident(incident_id: int, body: IncidentPatch, user: dict = _auth):
    _require_write(user)

    pool = get_pool()
    async with pool.acquire() as conn:
        inc = await _fetch_incident(conn, incident_id)
        if not inc:
            raise HTTPException(404, "Incident not found")

        new_status = body.status or inc["status"]
        if body.status and body.status not in VALID_STATUSES:
            raise HTTPException(400, f"status must be one of {VALID_STATUSES}")

        # Closing requires a non-empty resolution
        if new_status == "closed":
            resolution = (body.resolution or inc.get("resolution") or "").strip()
            if not resolution:
                raise HTTPException(400, "A resolution is required to close an incident")

        now = datetime.now(timezone.utc)
        closed_at = now if (new_status == "closed" and inc["status"] != "closed") else inc.get("closed_at")
        # Re-open: clear closed_at
        if new_status != "closed":
            closed_at = None

        await conn.execute(
            """
            UPDATE incidents
            SET    status      = COALESCE($1, status),
                   assigned_to = COALESCE($2, assigned_to),
                   resolution  = COALESCE($3, resolution),
                   title       = COALESCE($4, title),
                   description = COALESCE($5, description),
                   updated_at  = $6,
                   closed_at   = $7
            WHERE  id = $8
            """,
            body.status,
            body.assigned_to,
            body.resolution,
            body.title,
            body.description,
            now,
            closed_at,
            incident_id,
        )

        await _log_activity(
            conn, "incident_updated",
            inc["device_id"], inc["alert_id"],
            user["username"],
            f"Incident #{incident_id} → {new_status}" + (f" (assigned: {body.assigned_to})" if body.assigned_to else ""),
        )

        return await _fetch_incident(conn, incident_id)


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/incidents/{id}/notes
# ══════════════════════════════════════════════════════════════════════════════

class NoteCreate(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000)


@router.post("/{incident_id}/notes", status_code=201)
async def add_note(incident_id: int, body: NoteCreate, user: dict = _auth):
    _require_write(user)

    pool = get_pool()
    async with pool.acquire() as conn:
        inc = await _fetch_incident(conn, incident_id)
        if not inc:
            raise HTTPException(404, "Incident not found")

        note_id = await conn.fetchval(
            """
            INSERT INTO incident_notes (incident_id, note, author)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            incident_id,
            body.note,
            user["username"],
        )

        # Bump updated_at on the incident
        await conn.execute(
            "UPDATE incidents SET updated_at = NOW() WHERE id = $1",
            incident_id,
        )

        await _log_activity(
            conn, "incident_note_added",
            inc["device_id"], inc["alert_id"],
            user["username"],
            f"Note on incident #{incident_id}",
        )

        row = await conn.fetchrow(
            "SELECT id, incident_id, note, author, created_at FROM incident_notes WHERE id = $1",
            note_id,
        )
        return dict(row)
