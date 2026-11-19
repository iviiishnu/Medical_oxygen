"""
integration/alerts.py
=====================
process_alert_state(conn, message, message_id)

Called by the tablet ingestion router after a message has been stored and
device last_seen_at has been updated — but only for real (non-test, non-
duplicate) messages.

Rules (from portal-guide and steering/rules.md):
1. Only the newest message (by tablet timestamp) may open or close an alert.
   If msg.timestamp <= tablet_devices.latest_message_at, store as usual but
   skip alert logic entirely.  Otherwise update latest_message_at first.
2. alert_status == CRITICAL, no open PANEL_CRITICAL alert:  open one.
3. alert_status == CRITICAL, open alert exists:  update worst_status /
   severity if this message is worse (using the status priority order from
   the portal guide).
4. alert_status == NORMAL:  close any open PANEL_CRITICAL alert by setting
   cleared_at to the message timestamp.
5. alert_status == UNREADABLE:  no PANEL_CRITICAL action here; clearing of
   UNREADABLE watchdog alerts is handled below (rule W2).
6. On every accepted (newest) message:
   W1 — if a TABLET_OFFLINE alert is open, clear it and restore device status.
   W2 — if alert_status != UNREADABLE and an UNREADABLE alert is open, clear it.
7. All alert opens/closes broadcast {"type":"alert","device_id":...} via ws_manager
   and append a row to activity_log.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.models.tablet import TabletMessage

# ── Status priority ───────────────────────────────────────────────────────────
_STATUS_RANK: dict[str, int] = {
    "NEAR_LOW":  1,
    "NEAR_HIGH": 1,
    "LOW":       2,
    "HIGH":      2,
    "CRITICAL":  3,
}


def _worst_gauge_status(msg: TabletMessage) -> str | None:
    best: str | None = None
    best_rank = 0
    for gauge in msg.gauges:
        rank = _STATUS_RANK.get(gauge.status or "", 0)
        if rank > best_rank:
            best_rank = rank
            best = gauge.status
    return best


def _is_worse(new_status: str | None, current_status: str | None) -> bool:
    return _STATUS_RANK.get(new_status or "", 0) > _STATUS_RANK.get(current_status or "", 0)


def _severity_from_status(status: str | None) -> str:
    rank = _STATUS_RANK.get(status or "", 0)
    if rank >= 3:
        return "CRITICAL"
    if rank == 2:
        return "HIGH"
    if rank == 1:
        return "MEDIUM"
    return "LOW"


async def _log_activity(
    conn: Any,
    event_type: str,
    device_id: str,
    alert_id: int | None,
    detail: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO activity_log (event_type, device_id, alert_id, actor, detail)
        VALUES ($1, $2, $3, 'system', $4)
        """,
        event_type, device_id, alert_id, detail,
    )


async def process_alert_state(
    conn: Any,
    msg: TabletMessage,
    message_id: int,
) -> None:
    """
    Evaluate alert state for one ingested message.

    Parameters
    ----------
    conn        asyncpg connection (already acquired by the caller)
    msg         normalised TabletMessage
    message_id  row id just inserted into tablet_messages
    """
    # Import here to avoid circular import at module level
    from app.ws_manager import manager

    # ── 1. Is this the newest message for this device? ────────────────────
    row = await conn.fetchrow(
        "SELECT latest_message_at FROM tablet_devices WHERE device_id = $1",
        msg.device_id,
    )
    latest_at = row["latest_message_at"] if row else None

    if latest_at is not None and msg.timestamp <= latest_at:
        # Late-arriving or replayed message — already stored, skip alert logic.
        return

    # Update latest_message_at to this message's timestamp.
    await conn.execute(
        """
        UPDATE tablet_devices
        SET    latest_message_at = $1
        WHERE  device_id = $2
        """,
        msg.timestamp,
        msg.device_id,
    )

    alert_status = (msg.alert_status or "").upper()
    broadcasted  = False  # track whether we already broadcast for this message

    # ── W1. Clear any open TABLET_OFFLINE alert ───────────────────────────
    offline_alert = await conn.fetchrow(
        """
        SELECT id FROM tablet_alerts
        WHERE  device_id  = $1
          AND  alert_type = 'TABLET_OFFLINE'
          AND  cleared_at IS NULL
        LIMIT 1
        """,
        msg.device_id,
    )
    if offline_alert:
        await conn.execute(
            """
            UPDATE tablet_alerts
            SET    cleared_at = $1
            WHERE  id = $2
            """,
            msg.timestamp,
            offline_alert["id"],
        )
        # Restore device status from this message's alert_status
        restored = alert_status if alert_status else "UNKNOWN"
        await conn.execute(
            "UPDATE tablet_devices SET status = $1 WHERE device_id = $2",
            restored,
            msg.device_id,
        )
        await _log_activity(
            conn, "device_online", msg.device_id, offline_alert["id"],
            "Device came back online",
        )
        await manager.broadcast({"type": "alert", "device_id": msg.device_id})
        broadcasted = True

    # ── W2. Clear any open UNREADABLE alert if status is no longer UNREADABLE
    if alert_status != "UNREADABLE":
        unreadable_alert = await conn.fetchrow(
            """
            SELECT id FROM tablet_alerts
            WHERE  device_id  = $1
              AND  alert_type = 'UNREADABLE'
              AND  cleared_at IS NULL
            LIMIT 1
            """,
            msg.device_id,
        )
        if unreadable_alert:
            await conn.execute(
                """
                UPDATE tablet_alerts
                SET    cleared_at = $1
                WHERE  id = $2
                """,
                msg.timestamp,
                unreadable_alert["id"],
            )
            await _log_activity(
                conn, "alert_cleared", msg.device_id, unreadable_alert["id"],
                "Device no longer UNREADABLE",
            )
            if not broadcasted:
                await manager.broadcast({"type": "alert", "device_id": msg.device_id})
                broadcasted = True

    # ── 2 & 3. CRITICAL ──────────────────────────────────────────────────
    if alert_status == "CRITICAL":
        open_alert = await conn.fetchrow(
            """
            SELECT id, worst_status, severity
            FROM   tablet_alerts
            WHERE  device_id  = $1
              AND  alert_type = 'PANEL_CRITICAL'
              AND  cleared_at IS NULL
            ORDER  BY started_at DESC
            LIMIT  1
            """,
            msg.device_id,
        )

        worst        = _worst_gauge_status(msg)
        # Pass the Python list directly; asyncpg serialises it as a proper
        # JSON array when bound to a jsonb column.  Using json.dumps() would
        # produce a double-encoded string stored as a JSON string scalar.
        reasons_list = msg.reasons  # already list[str]

        if open_alert is None:
            # Rule 2: open a new alert.
            severity = _severity_from_status(worst)
            alert_id = await conn.fetchval(
                """
                INSERT INTO tablet_alerts
                    (device_id, alert_type, severity, started_at,
                     worst_status, reasons, confidence_pct, start_message_id)
                VALUES ($1, 'PANEL_CRITICAL', $2, $3, $4, $5::jsonb, $6, $7)
                RETURNING id
                """,
                msg.device_id,
                severity,
                msg.timestamp,
                worst,
                json.dumps(reasons_list),
                msg.confidence_pct,
                message_id,
            )
            await _log_activity(
                conn, "alert_opened", msg.device_id, alert_id,
                f"CRITICAL: {worst}",
            )
            if not broadcasted:
                await manager.broadcast({"type": "alert", "device_id": msg.device_id})
                broadcasted = True
        else:
            # Rule 3: escalate only if this message is worse.
            if _is_worse(worst, open_alert["worst_status"]):
                new_severity = _severity_from_status(worst)
                await conn.execute(
                    """
                    UPDATE tablet_alerts
                    SET    worst_status = $1,
                           severity     = $2,
                           reasons      = $3::jsonb
                    WHERE  id = $4
                    """,
                    worst,
                    new_severity,
                    json.dumps(reasons_list),
                    open_alert["id"],
                )
                if not broadcasted:
                    await manager.broadcast({"type": "alert", "device_id": msg.device_id})
                    broadcasted = True

    # ── 4. NORMAL — close any open PANEL_CRITICAL alert ───────────────────
    elif alert_status == "NORMAL":
        closed = await conn.fetchrow(
            """
            UPDATE tablet_alerts
            SET    cleared_at = $1
            WHERE  device_id  = $2
              AND  alert_type = 'PANEL_CRITICAL'
              AND  cleared_at IS NULL
            RETURNING id
            """,
            msg.timestamp,
            msg.device_id,
        )
        if closed:
            await _log_activity(
                conn, "alert_cleared", msg.device_id, closed["id"],
                "Panel returned to NORMAL",
            )
            if not broadcasted:
                await manager.broadcast({"type": "alert", "device_id": msg.device_id})
                broadcasted = True

    # ── Broadcast reading event (always, for live dashboard updates) ───────
    await manager.broadcast({"type": "reading", "device_id": msg.device_id})
