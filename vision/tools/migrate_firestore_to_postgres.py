"""One-time, idempotent import of legacy Firestore monitoring data into PostgreSQL.

Set DATABASE_URL, GOOGLE_APPLICATION_CREDENTIALS, and FIREBASE_PROJECT_ID, then run:
    python vision/tools/migrate_firestore_to_postgres.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import firebase_admin
from firebase_admin import firestore
from o2gauge import postgres_store as store
from psycopg.types.json import Jsonb


def normalized(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): normalized(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalized(v) for v in value]
    if hasattr(value, "to_dict"):
        return normalized(value.to_dict())
    return value


def timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def main() -> None:
    if not store.configured():
        raise RuntimeError("Install vision/requirements-run.txt and set DATABASE_URL before migrating.")
    project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GCLOUD_PROJECT")
    firebase_admin.initialize_app(options={"projectId": project_id} if project_id else None)
    fs = firestore.client()
    counts = {"staff": 0, "devices": 0, "readings": 0, "alerts": 0}

    with store.connection() as conn:
        for doc in fs.collection("staff").stream():
            data = doc.to_dict() or {}
            conn.execute(
                """INSERT INTO staff(uid,email,display_name,role,on_duty,escalation_order,fcm_tokens)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(uid) DO NOTHING""",
                (doc.id, data.get("email") or doc.id, data.get("name") or "", data.get("role") or "staff",
                 bool(data.get("on_duty", True)), int(data.get("escalation_order") or 1),
                 list(data.get("fcm_tokens") or [])),
            )
            counts["staff"] += 1

        for doc in fs.collection("devices").stream():
            data = doc.to_dict() or {}
            config = data.get("config") or {}
            gauges = config.get("gauges") or []
            primary = next((g for g in gauges if not g.get("ignored")), {})
            creator = data.get("created_by")
            if creator and not conn.execute("SELECT 1 FROM staff WHERE uid=%s", (creator,)).fetchone():
                creator = None
            conn.execute(
                """INSERT INTO devices(id,name,created_by,status,alarm,online,trend_falling,battery,last_heartbeat,
                   last_reading,low_threshold,critical_threshold,registration_image,created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING""",
                (doc.id, data.get("name") or doc.id, creator, data.get("status") or "UNKNOWN",
                 data.get("alarm") or "OK", bool(data.get("online", False)), bool(data.get("trend_falling", False)),
                 data.get("battery"), data.get("last_heartbeat"), Jsonb(normalized(data.get("last_reading") or {})),
                 float(config.get("low_threshold", primary.get("low_threshold", 3.5))),
                 float(config.get("critical_threshold", primary.get("critical_threshold", 3.0))),
                 data.get("registration_image"), timestamp(data.get("created_at"))),
            )
            for i, gauge in enumerate(gauges):
                number = int(gauge.get("number", i + 1))
                conn.execute(
                    """INSERT INTO device_gauges(device_id,number,name,unit,kind,scale,reading,confidence_pct,
                       low_threshold,critical_threshold,ignored) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(device_id,number) DO NOTHING""",
                    (doc.id, number, str(gauge.get("name") or f"Gauge {number}"), str(gauge.get("unit") or "unknown"),
                     str(gauge.get("kind") or "analog"), float(gauge.get("scale") or 0), gauge.get("reading"),
                     int(gauge.get("confidence_pct") or 0), gauge.get("low_threshold"), gauge.get("critical_threshold"),
                     bool(gauge.get("ignored"))),
                )
            counts["devices"] += 1
            gauge_number = int(primary.get("number", 1))
            for reading in doc.reference.collection("readings").stream():
                point = reading.to_dict() or {}
                captured = point.get("server_ts") or point.get("ts")
                value = point.get("smoothed", point.get("value"))
                conn.execute(
                    """INSERT INTO readings(device_id,gauge_number,captured_at,value,unit,status,confidence_pct,payload)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (doc.id, gauge_number, timestamp(captured), value, str(point.get("unit") or "kg/cm2"),
                     str(point.get("status") or "UNKNOWN"), point.get("confidence_pct"), Jsonb(normalized(point))),
                )
                counts["readings"] += 1

        for doc in fs.collection("alerts").stream():
            data = doc.to_dict() or {}
            device_id = str(data.get("device_id") or "legacy-unknown")
            if not conn.execute("SELECT 1 FROM devices WHERE id=%s", (device_id,)).fetchone():
                conn.execute("INSERT INTO devices(id,name) VALUES (%s,%s) ON CONFLICT(id) DO NOTHING",
                             (device_id, device_id))
            acked_by = data.get("acked_by")
            if acked_by and not conn.execute("SELECT 1 FROM staff WHERE uid=%s", (acked_by,)).fetchone():
                acked_by = None
            conn.execute(
                """INSERT INTO alerts(id,device_id,type,state,value,unit,reason,created_at,acked_by,acked_by_name,
                   acked_at,ack_reason,ack_resolution,ack_notes,resolved_at,escalation_level,evidence_image)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING""",
                (doc.id, device_id, str(data.get("type") or "UNKNOWN"), str(data.get("state") or "OPEN"),
                 data.get("value"), str(data.get("unit") or "kg/cm2"), data.get("reason"),
                 timestamp(data.get("created_at")), acked_by, data.get("acked_by_name"), data.get("acked_at"),
                 data.get("ack_reason"), data.get("ack_resolution"), data.get("ack_notes"), data.get("resolved_at"),
                 int(data.get("escalation_level") or 0), data.get("evidence_image") or data.get("image")),
            )
            counts["alerts"] += 1

    print("Firestore import complete (existing PostgreSQL rows were left unchanged):")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
