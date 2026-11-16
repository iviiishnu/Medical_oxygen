# Architecture and interface contract

```
Mobile camera / dashboard browser
      │ PostgreSQL-backed signed session + JSON / multipart HTTPS requests
      ▼
Python monitoring API + vision model
      ├── PostgreSQL: staff, registered devices/gauges, current readings,
      │               one-minute history, alerts, evidence and acknowledgement reports
```

PostgreSQL is the only database and account store. The backend validates expiring sessions signed
with `AUTH_SECRET` and is the only app component that connects to PostgreSQL. The mobile app and
dashboard share the same API and records.

The mobile live reader sends one camera frame per second to `/api/read` with a registered device ID.
The backend uses the stored gauge include list and thresholds, responds with JSON for ordinary
frames, stores the latest reading on every frame, and adds one history point per enabled gauge per
minute. It stores an annotated evidence image only when a new alert is raised. Initial device
registration photos and acknowledgement reports are stored with their corresponding PostgreSQL
records.

The backend checks device heartbeats every 10 seconds, raises `TABLET_OFFLINE` after two missed
30-second heartbeats plus grace, and escalates unacknowledged alerts every two minutes. Clients poll
PostgreSQL-backed alert state while open. Background push delivery is not configured.

## Reading message (per frame) - `contract/reading.schema.json`

```json
{"device_id": "tab-main-o2-01", "gauge_id": "oxygen_main", "ts": "2026-11-20T10:15:02+05:30",
 "value": 5.4, "unit": "kg/cm2", "confidence": 0.93, "lamp_state": "NORMAL",
 "method_agree": true, "status": "OK"}
```

* `value` is `null` when no method can read the needle.
* `lamp_state`: NORMAL | LOW | HIGH | OFF | CONFLICT | UNKNOWN. Unknown or conflicting lamps are
  not silently mapped to a real state.
* `status` is the individual frame classification; an alert transition is stored separately in
  PostgreSQL with the acknowledging user's reason and resolution.

## Shared files (single source of truth)

| File | Used by |
|---|---|
| `contract/reading.schema.json` | Python pipeline and integrations |
| `contract/monitor_config.default.json` | default thresholds and timings |
| `contract/alert_scenarios.json` | alert engine test vectors |
| `contract/stage_b_spec.md` | TFLite input/output layout and post-processing |
| `vision/o2gauge/postgres_schema.sql` | PostgreSQL tables and indexes (initialized by the API) |

## Geometry convention

Dial angle = degrees clockwise from 12 o'clock, image y axis down. Value is linear between the
tapped 0 mark and max mark, clockwise. Needle angles within 4° beyond either end are clamped and
still valid; deeper into the bottom gap they are flagged out-of-range (confidence halved).
