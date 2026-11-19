"""
integration/watchdog.py
=======================
Background watchdog that runs every 15 seconds and checks every known
tablet device for two conditions:

1. TABLET_OFFLINE  — no message received in the last 90 seconds.
   Opens a tablet_alert of type TABLET_OFFLINE (severity OFFLINE) if none
   is open; sets tablet_devices.status = 'OFFLINE'.
   Clears the alert (sets cleared_at) when a live message arrives; that
   clearing is hooked into process_alert_state in integration/alerts.py.

2. UNREADABLE      — the latest message has alert_status == 'UNREADABLE'
   and that run has lasted more than 120 seconds.
   Opens a tablet_alert of type UNREADABLE (severity UNREADABLE) if none
   is open.  Clears it on the next non-UNREADABLE message via
   process_alert_state.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from app.db.database import get_pool
from app.ws_manager import manager


_OFFLINE_SECONDS     = 90
_UNREADABLE_SECONDS  = 120
_POLL_INTERVAL       = 15


async def _log_activity(conn, event_type: str, device_id: str,
                        alert_id: int | None, detail: str) -> None:
    await conn.execute(
        """
        INSERT INTO activity_log (event_type, device_id, alert_id, actor, detail)
        VALUES ($1, $2, $3, 'watchdog', $4)
        """,
        event_type, device_id, alert_id, detail,
    )


async def _run_once() -> None:
    pool = get_pool()
    now = datetime.now(timezone.utc)
    offline_cutoff     = now - timedelta(seconds=_OFFLINE_SECONDS)
    unreadable_cutoff  = now - timedelta(seconds=_UNREADABLE_SECONDS)

    async with pool.acquire() as conn:
        devices = await conn.fetch(
            """
            SELECT device_id, last_seen_at, status, latest_message_at
            FROM   tablet_devices
            """
        )

        for dev in devices:
            device_id    = dev["device_id"]
            last_seen    = dev["last_seen_at"]      # may be None for brand-new device
            current_status = dev["status"]

            # ── 1. Offline check ──────────────────────────────────────────
            is_offline = (last_seen is None or last_seen < offline_cutoff)

            if is_offline:
                # Is there already an open TABLET_OFFLINE alert?
                open_offline = await conn.fetchrow(
                    """
                    SELECT id FROM tablet_alerts
                    WHERE  device_id  = $1
                      AND  alert_type = 'TABLET_OFFLINE'
                      AND  cleared_at IS NULL
                    LIMIT 1
                    """,
                    device_id,
                )
                if open_offline is None:
                    alert_id = await conn.fetchval(
                        """
                        INSERT INTO tablet_alerts
                            (device_id, alert_type, severity, started_at)
                        VALUES ($1, 'TABLET_OFFLINE', 'OFFLINE', $2)
                        RETURNING id
                        """,
                        device_id,
                        now,
                    )
                    await conn.execute(
                        "UPDATE tablet_devices SET status = 'OFFLINE' WHERE device_id = $1",
                        device_id,
                    )
                    await _log_activity(
                        conn, "device_offline", device_id, alert_id,
                        f"No message for >{_OFFLINE_SECONDS}s",
                    )
                    await manager.broadcast({"type": "alert", "device_id": device_id})

            # ── 2. UNREADABLE check ───────────────────────────────────────
            # Only meaningful when the device is currently sending (not offline).
            if not is_offline and current_status == "UNREADABLE":
                # Find when the UNREADABLE run started: the timestamp of the
                # first UNREADABLE message in the current consecutive run.
                unreadable_since = await conn.fetchval(
                    """
                    SELECT MIN(timestamp)
                    FROM   tablet_messages
                    WHERE  device_id    = $1
                      AND  alert_status = 'UNREADABLE'
                      AND  timestamp   >= (
                              -- last non-UNREADABLE message timestamp, or epoch
                              SELECT COALESCE(MAX(timestamp), '1970-01-01'::TIMESTAMPTZ)
                              FROM   tablet_messages
                              WHERE  device_id    = $1
                                AND  alert_status <> 'UNREADABLE'
                          )
                    """,
                    device_id,
                )

                if unreadable_since is not None and unreadable_since < unreadable_cutoff:
                    open_unreadable = await conn.fetchrow(
                        """
                        SELECT id FROM tablet_alerts
                        WHERE  device_id  = $1
                          AND  alert_type = 'UNREADABLE'
                          AND  cleared_at IS NULL
                        LIMIT 1
                        """,
                        device_id,
                    )
                    if open_unreadable is None:
                        alert_id = await conn.fetchval(
                            """
                            INSERT INTO tablet_alerts
                                (device_id, alert_type, severity, started_at)
                            VALUES ($1, 'UNREADABLE', 'UNREADABLE', $2)
                            RETURNING id
                            """,
                            device_id,
                            unreadable_since,
                        )
                        await _log_activity(
                            conn, "alert_opened", device_id, alert_id,
                            f"UNREADABLE for >{_UNREADABLE_SECONDS}s",
                        )
                        await manager.broadcast({"type": "alert", "device_id": device_id})


async def watchdog_loop() -> None:
    """Entry point: run forever, one check every _POLL_INTERVAL seconds."""
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            await _run_once()
        except Exception as exc:
            print(f"⚠️  Watchdog error: {exc}")
