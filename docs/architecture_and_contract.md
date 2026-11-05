# Architecture and interface contract

```
Tablet (Monitor mode) -------------------------------------------------------------
  CameraX frame every 1 s (focus + exposure locked)
     -> GaugeReader            Stage A (classical) + Stage B (keypoint TFLite) + lamp reader
     -> Fusion                 one JSON reading (contract below)
     -> AlertEngine            median-5, 3-in-a-row, hysteresis, trend, fail-safe
     -> LocalAlarm             sound + flash, works with NO internet
     -> Firestore              latest reading, 1/min history, alerts, heartbeat every 30 s
Firebase ----------------------------------------------------------------------------
  Cloud Functions: onAlertCreated -> FCM high-priority to on-duty staff
                   escalation every minute (unacknowledged -> next person)
                   heartbeat watchdog (2 missed = TABLET_OFFLINE)
Staff phones (Staff mode): live status, full-screen alarm, Acknowledge
Desktop dashboard (web):   live value, 24 h chart, alert log, browser alarm sound
```

The tablet decides on its own. Firebase only fans out alerts and stores history,
so a Wi-Fi outage never silences the local alarm.

## Reading message (per frame) - `contract/reading.schema.json`

```json
{"device_id": "tab-main-o2-01", "gauge_id": "oxygen_main", "ts": "2026-11-20T10:15:02+05:30",
 "value": 5.4, "unit": "kg/cm2", "confidence": 0.93, "lamp_state": "NORMAL",
 "method_agree": true, "status": "OK"}
```

* `value` is `null` when no method can read the needle.
* `lamp_state`: NORMAL | LOW | HIGH | OFF (no lamp lit) | CONFLICT (several lit) | UNKNOWN (no lamps calibrated).
  OFF/CONFLICT/UNKNOWN were added to the original contract so "can't tell" is never silently mapped to a real state.
* `status` in the per-frame message is the *frame's* classification. The *alarm* state comes
  from the AlertEngine (same enum) and is what gets pushed to phones.

## Shared files (single source of truth)

| File | Used by |
|---|---|
| `contract/reading.schema.json` | Python pipeline tests, Kotlin, Cloud Functions validation |
| `contract/monitor_config.default.json` | thresholds + timings for every component |
| `contract/alert_scenarios.json` | the SAME test vectors run by the Python and Kotlin alert engines |
| `contract/stage_b_spec.md` | TFLite input/output layout and post-processing (Phase 3) |

## Geometry convention
Dial angle = degrees clockwise from 12 o'clock, image y axis down. Value is linear between the
tapped 0 mark and max mark, clockwise. Needle angles within 4° beyond either end are clamped
and still valid; deeper into the bottom gap they are flagged out-of-range (confidence halved).
