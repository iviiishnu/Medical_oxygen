"""PostgreSQL persistence for the authenticated monitoring API."""
from __future__ import annotations

import os
import re
import math
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

try:
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    from psycopg_pool import ConnectionPool
except ImportError:  # Keep the vision-only demo usable before optional server deps are installed.
    dict_row = Jsonb = ConnectionPool = None  # type: ignore[assignment,misc]


def _load_repo_env() -> None:
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if not match or match.group(1) in os.environ:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ[match.group(1)] = value


_load_repo_env()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
_pool: Any = None
_pool_lock = threading.Lock()
_schema_lock = threading.Lock()
_schema_ready = False


class StoreUnavailable(RuntimeError):
    pass


def configured() -> bool:
    return bool(DATABASE_URL and ConnectionPool is not None)


def healthy() -> bool:
    if not configured():
        return False
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
        return True
    except StoreUnavailable:
        return False


def _get_pool() -> Any:
    global _pool
    if not DATABASE_URL:
        raise StoreUnavailable("DATABASE_URL is not configured on the backend.")
    if ConnectionPool is None:
        raise StoreUnavailable("Install the PostgreSQL backend dependencies from vision/requirements-run.txt.")
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=8, timeout=5,
                                      kwargs={"row_factory": dict_row}, open=False)
                _pool.open(wait=False)
    return _pool


@contextmanager
def connection() -> Iterator[Any]:
    global _schema_ready
    pool = _get_pool()
    try:
        with pool.connection() as conn:
            if not _schema_ready:
                with _schema_lock:
                    if not _schema_ready:
                        schema = Path(__file__).with_name("postgres_schema.sql").read_text(encoding="utf-8")
                        conn.execute(schema, prepare=False)
                        conn.commit()
                        _schema_ready = True
            yield conn
    except StoreUnavailable:
        raise
    except Exception as exc:
        raise StoreUnavailable(f"PostgreSQL is unavailable: {exc}") from exc


def _json(value: Any) -> Any:
    return Jsonb(value)


def _millis(value: datetime | None) -> int | None:
    return int(value.timestamp() * 1000) if value else None


def _numeric_scale(value: Any) -> float:
    """Model scale labels can contain units/provenance; persist only a numeric scale limit."""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else 0.0
    if isinstance(value, str):
        match = re.search(r"(-?\d+(?:\.\d+)?)\s*[-–—]\s*(-?\d+(?:\.\d+)?)", value)
        if match:
            number = float(match.group(2))
            return number if math.isfinite(number) and number >= 0 else 0.0
        try:
            number = float(value.strip())
        except ValueError:
            return 0.0
        return number if math.isfinite(number) and number >= 0 else 0.0
    return 0.0


def ensure_staff(conn: Any, claims: dict[str, Any]) -> None:
    uid = str(claims.get("uid") or claims.get("sub") or "")
    email = str(claims.get("email") or "")
    role = str(claims.get("role") or "")
    if not uid or not email or role not in ("staff", "admin"):
        raise ValueError("The sign-in token must include a user ID and email.")
    row = conn.execute("SELECT 1 FROM staff WHERE uid=%s AND is_active=TRUE AND role=%s", (uid, role)).fetchone()
    if not row:
        raise PermissionError("This PostgreSQL account is inactive or no longer has staff access.")


def _device(row: dict[str, Any], gauges: list[dict[str, Any]]) -> dict[str, Any]:
    latest = row.get("last_reading") or {}
    return {
        "id": row["id"], "name": row["name"],
        "value": latest.get("reading"), "unit": latest.get("unit") or "kg/cm2",
        "status": row["status"], "alarm": row["alarm"], "trendFalling": row["trend_falling"],
        "lastHeartbeatMs": _millis(row["last_heartbeat"]), "online": row["online"],
        "battery": row["battery"], "lowThreshold": row["low_threshold"],
        "criticalThreshold": row["critical_threshold"],
        "highThreshold": next((g.get("highThreshold") for g in gauges if not g.get("ignored")), None),
        "gauges": gauges,
    }


def list_devices(claims: dict[str, Any]) -> list[dict[str, Any]]:
    with connection() as conn:
        ensure_staff(conn, claims)
        devices = conn.execute("SELECT * FROM devices ORDER BY name").fetchall()
        gauges = conn.execute("SELECT * FROM device_gauges ORDER BY device_id,number").fetchall()
    by_device: dict[str, list[dict[str, Any]]] = {}
    for g in gauges:
        by_device.setdefault(g["device_id"], []).append({
            "number": g["number"], "name": g["name"], "unit": g["unit"], "kind": g["kind"],
            "scale": g["scale"], "reading": g["reading"], "confidencePct": g["confidence_pct"],
            "lowThreshold": g["low_threshold"], "criticalThreshold": g["critical_threshold"],
            "highThreshold": g["high_threshold"],
            "ignored": g["ignored"],
        })
    return [_device(d, by_device.get(d["id"], [])) for d in devices]


def register_device(claims: dict[str, Any], registration: dict[str, Any]) -> None:
    uid = str(claims.get("uid") or claims.get("sub") or "")
    name = str(registration.get("name") or "").strip()
    device_id = str(registration.get("id") or "").strip()
    gauges = registration.get("gauges")
    image = registration.get("registrationImage")
    if not name or len(name) > 120 or not device_id or len(device_id) > 120:
        raise ValueError("Enter a panel name and a valid device ID.")
    if not isinstance(gauges, list) or not gauges or any(not isinstance(g, dict) for g in gauges):
        raise ValueError("The image did not contain a readable gauge.")
    included = [g for g in gauges if not g.get("ignored")]
    try:
        invalid_thresholds = any(
            g.get("lowThreshold") is None or g.get("criticalThreshold") is None or
            float(g["criticalThreshold"]) >= float(g["lowThreshold"]) or
            (g.get("highThreshold") is not None and float(g["highThreshold"]) <= float(g["lowThreshold"]))
            for g in included
        )
    except (TypeError, ValueError):
        invalid_thresholds = True
    if not included or invalid_thresholds:
        raise ValueError("Each included gauge needs Critical below Low; an optional High threshold must be above Low.")
    if not isinstance(image, str) or len(image) > 750_000:
        raise ValueError("Registration image is missing or exceeds the 500 KB limit.")
    main = included[0]
    with connection() as conn:
        ensure_staff(conn, claims)
        conn.execute(
            """INSERT INTO devices(id,name,created_by,low_threshold,critical_threshold,registration_image)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT(id) DO UPDATE SET name=EXCLUDED.name, created_by=EXCLUDED.created_by,
                 low_threshold=EXCLUDED.low_threshold, critical_threshold=EXCLUDED.critical_threshold,
                 registration_image=EXCLUDED.registration_image, updated_at=NOW()""",
            (device_id, name, uid, main["lowThreshold"], main["criticalThreshold"], image),
        )
        conn.execute("DELETE FROM device_gauges WHERE device_id=%s", (device_id,))
        for g in gauges:
            conn.execute(
                """INSERT INTO device_gauges(device_id,number,name,unit,kind,scale,reading,confidence_pct,
                   low_threshold,critical_threshold,high_threshold,ignored) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (device_id, int(g["number"]), str(g.get("name") or f"Gauge {g['number']}"),
                 str(g.get("unit") or "unknown"), str(g.get("kind") or "analog"), _numeric_scale(g.get("scale")),
                 g.get("reading"), int(g.get("confidencePct") or 0), g.get("lowThreshold"),
                 g.get("criticalThreshold"), g.get("highThreshold"), bool(g.get("ignored"))),
            )


def get_device_gauges(claims: dict[str, Any], device_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        ensure_staff(conn, claims)
        rows = conn.execute(
            "SELECT number,name,unit,kind,scale,low_threshold,critical_threshold,high_threshold,ignored FROM device_gauges WHERE device_id=%s ORDER BY number",
            (device_id,),
        ).fetchall()
        if not rows:
            exists = conn.execute("SELECT 1 FROM devices WHERE id=%s", (device_id,)).fetchone()
            if not exists:
                raise LookupError("The selected panel is not registered in PostgreSQL.")
    return [{
        "number": r["number"], "name": r["name"], "unit": r["unit"], "kind": r["kind"],
        "scale": r["scale"], "low_threshold": r["low_threshold"],
        "critical_threshold": r["critical_threshold"], "ignored": r["ignored"],
        "high_threshold": r["high_threshold"],
    } for r in rows]


def list_alerts(claims: dict[str, Any]) -> list[dict[str, Any]]:
    with connection() as conn:
        ensure_staff(conn, claims)
        rows = conn.execute(
            """SELECT a.*, s.email AS acked_by_email, s.display_name AS acked_by_display FROM alerts a LEFT JOIN staff s ON s.uid=a.acked_by
               WHERE a.created_at >= NOW() - INTERVAL '24 hours' ORDER BY a.created_at DESC LIMIT 300"""
        ).fetchall()
    return [{
        "id": r["id"], "type": r["type"], "state": r["state"], "deviceId": r["device_id"],
        "value": r["value"], "unit": r["unit"], "createdMs": _millis(r["created_at"]),
        "ackedBy": r["acked_by_name"] or r["acked_by_display"] or r["acked_by_email"], "ackedMs": _millis(r["acked_at"]),
        "resolvedMs": _millis(r["resolved_at"]), "escalationLevel": r["escalation_level"],
        "ackReason": r["ack_reason"], "ackResolution": r["ack_resolution"], "ackNotes": r["ack_notes"],
    } for r in rows]


def get_alert_details(claims: dict[str, Any], alert_id: str) -> dict[str, Any]:
    with connection() as conn:
        ensure_staff(conn, claims)
        row = conn.execute(
            """SELECT a.*, d.name AS device_name FROM alerts a JOIN devices d ON d.id=a.device_id WHERE a.id=%s""",
            (alert_id,),
        ).fetchone()
        if not row:
            raise LookupError("Alert not found.")
        gauge = conn.execute(
            """SELECT number,low_threshold,critical_threshold,high_threshold FROM device_gauges
               WHERE device_id=%s AND ignored=FALSE ORDER BY number LIMIT 1""", (row["device_id"],),
        ).fetchone()
        history = conn.execute(
            """SELECT captured_at,value,status FROM readings WHERE device_id=%s
               AND gauge_number=COALESCE(%s, (SELECT number FROM device_gauges WHERE device_id=%s AND ignored=FALSE ORDER BY number LIMIT 1))
               ORDER BY captured_at DESC LIMIT 50""", (row["device_id"], gauge["number"] if gauge else None, row["device_id"]),
        ).fetchall()
    return {
        "id": row["id"], "type": row["type"], "state": row["state"], "deviceId": row["device_id"],
        "deviceName": row["device_name"], "value": row["value"], "unit": row["unit"],
        "createdMs": _millis(row["created_at"]), "ackedBy": row["acked_by_name"],
        "ackedMs": _millis(row["acked_at"]), "resolvedMs": _millis(row["resolved_at"]),
        "escalationLevel": row["escalation_level"], "ackReason": row["ack_reason"],
        "ackResolution": row["ack_resolution"], "ackNotes": row["ack_notes"],
        "reason": row["reason"], "evidenceImage": row["evidence_image"],
        "lowThreshold": gauge["low_threshold"] if gauge else None,
        "criticalThreshold": gauge["critical_threshold"] if gauge else None,
        "highThreshold": gauge["high_threshold"] if gauge else None,
        "recentReadings": [{"t": _millis(p["captured_at"]), "v": p["value"], "status": p["status"]} for p in reversed(history)],
    }


def list_incidents(claims: dict[str, Any]) -> list[dict[str, Any]]:
    with connection() as conn:
        ensure_staff(conn, claims)
        rows = conn.execute(
            """SELECT i.*, COALESCE(s.display_name, s.email, 'Staff') AS creator_name
               FROM incidents i LEFT JOIN staff s ON s.uid=i.created_by
               ORDER BY i.updated_at DESC LIMIT 300"""
        ).fetchall()
        ids = [r["id"] for r in rows]
        updates = conn.execute(
            """SELECT u.*, COALESCE(s.display_name, s.email, 'Staff') AS author_name
               FROM incident_updates u LEFT JOIN staff s ON s.uid=u.author
               WHERE u.incident_id = ANY(%s) ORDER BY u.created_at ASC""", (ids,),
        ).fetchall() if ids else []
    updates_by_id: dict[str, list[dict[str, Any]]] = {}
    for u in updates:
        updates_by_id.setdefault(u["incident_id"], []).append({
            "id": u["id"], "note": u["note"], "actionTaken": u["action_taken"],
            "status": u["status"], "author": u["author_name"], "createdMs": _millis(u["created_at"]),
        })
    return [{
        "id": r["id"], "title": r["title"], "deviceId": r["device_id"], "alertId": r["alert_id"],
        "description": r["description"], "possibleCause": r["possible_cause"],
        "actionTaken": r["action_taken"], "assignedTo": r["assigned_to"], "status": r["status"],
        "createdBy": r["creator_name"], "createdMs": _millis(r["created_at"]),
        "updatedMs": _millis(r["updated_at"]), "updates": updates_by_id.get(r["id"], []),
    } for r in rows]


def create_incident(claims: dict[str, Any], incident: dict[str, Any]) -> str:
    title = str(incident.get("title") or "").strip()
    description = str(incident.get("description") or "").strip()
    device_id = str(incident.get("deviceId") or "").strip() or None
    alert_id = str(incident.get("alertId") or "").strip() or None
    possible_cause = str(incident.get("possibleCause") or "").strip() or None
    action_taken = str(incident.get("actionTaken") or "").strip() or None
    assigned_to = str(incident.get("assignedTo") or "").strip() or None
    if not title or len(title) > 160 or not description or len(description) > 5000:
        raise ValueError("Enter an incident title (up to 160 characters) and description (up to 5000 characters).")
    uid = str(claims.get("uid") or claims.get("sub") or "")
    incident_id = str(uuid.uuid4())
    with connection() as conn:
        ensure_staff(conn, claims)
        if device_id and not conn.execute("SELECT 1 FROM devices WHERE id=%s", (device_id,)).fetchone():
            raise LookupError("The selected device is not registered.")
        if alert_id:
            alert = conn.execute("SELECT device_id FROM alerts WHERE id=%s", (alert_id,)).fetchone()
            if not alert:
                raise LookupError("The selected alert was not found.")
            if device_id and alert["device_id"] != device_id:
                raise ValueError("The selected alert does not belong to this device.")
            device_id = device_id or alert["device_id"]
        conn.execute(
            """INSERT INTO incidents(id,title,device_id,alert_id,description,possible_cause,action_taken,assigned_to,created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (incident_id, title, device_id, alert_id, description, possible_cause, action_taken, assigned_to, uid),
        )
        conn.execute(
            "INSERT INTO incident_updates(id,incident_id,author,note,action_taken,status) VALUES (%s,%s,%s,%s,%s,'OPEN')",
            (str(uuid.uuid4()), incident_id, uid, "Incident created", action_taken),
        )
    return incident_id


def update_incident(claims: dict[str, Any], incident_id: str, change: dict[str, Any]) -> None:
    note = str(change.get("note") or "").strip()
    action_taken = str(change.get("actionTaken") or "").strip() or None
    status = str(change.get("status") or "").strip().upper() or None
    if not note or len(note) > 2000:
        raise ValueError("Add an update note (up to 2000 characters).")
    if status and status not in ("OPEN", "IN_PROGRESS", "CLOSED"):
        raise ValueError("Choose Open, In progress, or Closed.")
    uid = str(claims.get("uid") or claims.get("sub") or "")
    with connection() as conn:
        ensure_staff(conn, claims)
        row = conn.execute("SELECT status FROM incidents WHERE id=%s FOR UPDATE", (incident_id,)).fetchone()
        if not row:
            raise LookupError("Incident not found.")
        next_status = status or row["status"]
        conn.execute(
            """UPDATE incidents SET status=%s,action_taken=COALESCE(%s,action_taken),updated_at=NOW(),
               closed_at=CASE WHEN %s='CLOSED' THEN COALESCE(closed_at,NOW()) ELSE NULL END WHERE id=%s""",
            (next_status, action_taken, next_status, incident_id),
        )
        conn.execute(
            "INSERT INTO incident_updates(id,incident_id,author,note,action_taken,status) VALUES (%s,%s,%s,%s,%s,%s)",
            (str(uuid.uuid4()), incident_id, uid, note, action_taken, status),
        )


def get_history(claims: dict[str, Any], device_id: str, hours: int = 24) -> list[dict[str, Any]]:
    hours = max(1, min(720, int(hours)))
    bucket_minutes = 1 if hours <= 24 else 5 if hours <= 168 else 30
    with connection() as conn:
        ensure_staff(conn, claims)
        rows = conn.execute(
            """WITH ranked AS (
                 SELECT r.captured_at,r.value,r.status,
                        ROW_NUMBER() OVER (PARTITION BY floor(extract(epoch FROM r.captured_at)/(%s*60)) ORDER BY r.captured_at DESC) AS rn
                 FROM readings r WHERE r.device_id=%s
                   AND r.gauge_number=(SELECT number FROM device_gauges WHERE device_id=%s AND ignored=FALSE ORDER BY number LIMIT 1)
                   AND r.captured_at>=NOW()-make_interval(hours => %s)
               ) SELECT captured_at,value,status FROM ranked WHERE rn=1 ORDER BY captured_at ASC LIMIT 5000""",
            (bucket_minutes, device_id, device_id, hours),
        ).fetchall()
    return [{"t": _millis(r["captured_at"]), "v": r["value"], "status": r["status"]} for r in rows]


def acknowledge(claims: dict[str, Any], alert_id: str, report: dict[str, Any]) -> None:
    uid = str(claims.get("uid") or claims.get("sub") or "")
    reason = str(report.get("reason") or "").strip()
    resolution = str(report.get("resolution") or "").strip()
    notes = str(report.get("notes") or "").strip()
    if not reason or not resolution:
        raise ValueError("A reason and resolution are required to acknowledge an alert.")
    with connection() as conn:
        ensure_staff(conn, claims)
        row = conn.execute(
            """UPDATE alerts SET state='ACKED',acked_by=%s,acked_by_name=%s,acked_at=NOW(),ack_reason=%s,
               ack_resolution=%s,ack_notes=%s WHERE id=%s AND state='OPEN' RETURNING id""",
            (uid, claims.get("email") or uid, reason, resolution, notes, alert_id),
        ).fetchone()
        if not row:
            raise LookupError("Alert not found or it has already been acknowledged.")


def persist_reading(claims: dict[str, Any], device_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    uid = str(claims.get("uid") or claims.get("sub") or "")
    gauges = payload.get("gauges") if isinstance(payload.get("gauges"), list) else []
    alert = bool(payload.get("alert"))
    statuses = [str(g.get("status", "")) for g in gauges if isinstance(g, dict) and not g.get("ignored")]
    alarm = "CRITICAL" if "CRITICAL" in statuses else "HIGH" if "HIGH" in statuses else "LOW" if "LOW" in statuses else "UNCERTAIN" if payload.get("verdict") == "CAN'T TELL" else "OK"
    now = datetime.now(timezone.utc)
    events: list[dict[str, Any]] = []
    clean_payload = {k: v for k, v in payload.items() if k != "image"}
    with connection() as conn:
        ensure_staff(conn, claims)
        device = conn.execute("SELECT alarm FROM devices WHERE id=%s FOR UPDATE", (device_id,)).fetchone()
        if not device:
            raise LookupError("The selected panel is not registered in PostgreSQL.")
        conn.execute(
            """UPDATE devices SET status=%s,alarm=%s,online=TRUE,trend_falling=%s,last_heartbeat=%s,
               last_reading=%s,updated_at=NOW() WHERE id=%s""",
            (alarm if not alert else ("CRITICAL" if alarm == "CRITICAL" else "HIGH" if alarm == "HIGH" else "LOW" if alarm == "LOW" else "UNCERTAIN"),
             alarm if alert else "OK", bool(payload.get("trend_falling")), now,
             _json({"reading": payload.get("reading"), "unit": payload.get("unit"), "confidence_pct": payload.get("confidence_pct"), "gauges": gauges}), device_id),
        )
        offline_alerts = conn.execute(
            """UPDATE alerts SET state='RESOLVED',resolved_at=NOW() WHERE device_id=%s AND type='TABLET_OFFLINE'
               AND state IN ('OPEN','ACKED') RETURNING id""", (device_id,),
        ).fetchall()
        events.extend({"id": row["id"], "state": "RESOLVED"} for row in offline_alerts)
        last = conn.execute("SELECT MAX(captured_at) AS t FROM readings WHERE device_id=%s", (device_id,)).fetchone()["t"]
        if last is None or (now - last).total_seconds() >= 60:
            for g in gauges:
                if not isinstance(g, dict) or g.get("ignored"):
                    continue
                conn.execute(
                    """INSERT INTO readings(device_id,gauge_number,captured_at,value,unit,status,confidence_pct,payload)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (device_id, int(g.get("number") or 0), now, g.get("reading"), str(g.get("unit") or "unknown"),
                     str(g.get("status") or "UNCERTAIN"), g.get("confidence_pct"), _json(clean_payload)),
                )
        open_alert = conn.execute("SELECT id FROM alerts WHERE device_id=%s AND type<>'TABLET_OFFLINE' AND state IN ('OPEN','ACKED') ORDER BY created_at DESC LIMIT 1", (device_id,)).fetchone()
        if alert and not open_alert:
            kind = "CRITICAL" if "CRITICAL" in statuses else "HIGH" if "HIGH" in statuses else "LOW" if "LOW" in statuses else "UNCERTAIN"
            alert_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO alerts(id,device_id,type,value,unit,reason,evidence_image)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (alert_id, device_id, kind, payload.get("reading"), str(payload.get("unit") or "kg/cm2"),
                 "; ".join(map(str, payload.get("reasons") or [])), payload.get("image")),
            )
            events.append({"id": alert_id, "state": "OPEN", "device_id": device_id, "type": kind,
                           "value": payload.get("reading"), "unit": payload.get("unit") or "kg/cm2",
                           "escalation_level": 0})
        elif not alert and payload.get("verdict") == "NORMAL" and open_alert:
            resolved = conn.execute(
                "UPDATE alerts SET state='RESOLVED',resolved_at=NOW() WHERE device_id=%s AND state IN ('OPEN','ACKED') RETURNING id",
                (device_id,),
            ).fetchall()
            events.extend({"id": row["id"], "state": "RESOLVED"} for row in resolved)
    return events


def run_scheduled_jobs(escalation_after_s: int = 120, heartbeat_s: int = 30,
                       missed_heartbeats: int = 2, grace_s: int = 30) -> list[dict[str, Any]]:
    notifications: list[dict[str, Any]] = []
    with connection() as conn:
        stale = conn.execute(
            """SELECT id,last_heartbeat FROM devices WHERE online=TRUE
               AND (last_heartbeat IS NULL OR last_heartbeat < NOW()-make_interval(secs => %s)) FOR UPDATE""",
            (heartbeat_s * missed_heartbeats + grace_s,),
        ).fetchall()
        for device in stale:
            conn.execute("UPDATE devices SET online=FALSE,status='TABLET_OFFLINE',alarm='TABLET_OFFLINE',updated_at=NOW() WHERE id=%s",
                         (device["id"],))
            active = conn.execute(
                "SELECT id FROM alerts WHERE device_id=%s AND type='TABLET_OFFLINE' AND state IN ('OPEN','ACKED') LIMIT 1",
                (device["id"],),
            ).fetchone()
            if not active:
                alert_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO alerts(id,device_id,type,value,unit,reason,last_notified_at)
                       VALUES (%s,%s,'TABLET_OFFLINE',NULL,'kg/cm2',%s,NOW())""",
                    (alert_id, device["id"], f"No heartbeat since {device['last_heartbeat'] or 'never'}"),
                )
                notifications.append({"id": alert_id, "device_id": device["id"], "type": "TABLET_OFFLINE",
                                      "value": None, "unit": "kg/cm2", "escalation_level": 0})
        due = conn.execute(
            """SELECT id,device_id,type,value,unit,reason,escalation_level FROM alerts
               WHERE state='OPEN' AND last_notified_at < NOW()-make_interval(secs => %s) FOR UPDATE""",
            (escalation_after_s,),
        ).fetchall()
        for alert in due:
            next_level = int(alert["escalation_level"]) + 1
            conn.execute("UPDATE alerts SET escalation_level=%s,last_notified_at=NOW() WHERE id=%s",
                         (next_level, alert["id"]))
            notifications.append({**alert, "escalation_level": next_level})
    return notifications


def set_alert_state(alert_id: str, state: str) -> None:
    with connection() as conn:
        conn.execute("UPDATE alerts SET state=%s WHERE id=%s", (state, alert_id))
