#!/usr/bin/env python3
"""
mock_tablet.py – test sender for the Oxygen Flow Check Portal.

Usage:
    python tools/mock_tablet.py <scenario> [--device tab-01] [--url http://localhost:8000/api/readings]

Scenarios:
    normal        one status_change, oxygen 4.5 kg/cm2, NORMAL
    critical      one status_change, oxygen 2.5 kg/cm2, CRITICAL
    low           one status_change, oxygen 3.3 kg/cm2, LOW
    near_low      one status_change, oxygen 3.6 kg/cm2, NEAR_LOW
    unreadable    one status_change, UNREADABLE, confidence_pct null, gauges []
    heartbeat     one heartbeat with current (normal) readings
    duplicate     send the same message twice (same seq)
    out_of_order  three messages in order: newest, oldest, middle
    sequence      normal → critical → normal, 5 s apart
    multi         tab-01/02/03 NORMAL, then tab-02 CRITICAL after 5 s, then NORMAL

Rules applied here (the portal must also honour them):
    - seq starts at current epoch seconds and increments by 1 per message
      so it never collides with rows already in the database.
    - Each device keeps its own seq counter so seq values never collide
      across devices.
    - timestamp carries the +05:30 offset.
    - Every message has an OXYGEN gauge (number 1, kg/cm2) and
      a VACUUM gauge (number 3, mmHg).
    - alert_status and each gauge's status/status_text are set by this mock
      to match the reading (the portal never re-derives them).
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Gauge fixed configuration
# ---------------------------------------------------------------------------
IST = timezone(timedelta(hours=5, minutes=30))

O2_SAFE_LOW      = 3.5
O2_SAFE_HIGH     = 5.5
O2_SAFE_CRITICAL = 3.0
O2_SAFE_BUFFER   = 0.2

VAC_READING       = 579.4   # normal vacuum reading used in every message
VAC_SAFE_LOW      = 300.0
VAC_SAFE_HIGH     = None
VAC_SAFE_CRITICAL = 200.0
VAC_SAFE_BUFFER   = 25.0


# ---------------------------------------------------------------------------
# Per-device seq tracker
# ---------------------------------------------------------------------------
# Maps device_id → next seq to use.  Seeded from epoch seconds so values
# never collide with rows already stored in the database.
_seq_state: dict[str, int] = {}


def next_seq(device_id: str) -> int:
    """Return the next seq for this device and advance the counter."""
    if device_id not in _seq_state:
        _seq_state[device_id] = int(time.time())
    seq = _seq_state[device_id]
    _seq_state[device_id] += 1
    return seq


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def o2_gauge_status(reading):
    """Return (status, status_text) for an oxygen reading."""
    if reading is None:
        return "UNCERTAIN", "--"
    if reading < O2_SAFE_CRITICAL:
        return "CRITICAL", "CRITICALLY LOW"
    if reading < O2_SAFE_LOW:
        if reading >= O2_SAFE_LOW - O2_SAFE_BUFFER:
            return "NEAR_LOW", f"near low ({reading} kg/cm2, buffer {O2_SAFE_BUFFER})"
        return "LOW", f"below safe low ({reading} kg/cm2)"
    if reading <= O2_SAFE_LOW + O2_SAFE_BUFFER:
        return "NEAR_LOW", f"near low ({reading} kg/cm2)"
    if O2_SAFE_HIGH is not None and reading > O2_SAFE_HIGH:
        return "HIGH", f"above safe high ({reading} kg/cm2)"
    return "OK", "within the safe range"


def o2_alert_status(gauge_status):
    """Derive panel alert_status from the O2 gauge status."""
    if gauge_status in ("CRITICAL", "LOW", "HIGH"):
        return "CRITICAL"
    if gauge_status in ("NEAR_LOW", "NEAR_HIGH"):
        return "NORMAL"   # still within safe range
    return "NORMAL"


def vac_gauge(device_id):
    """Return the standard VACUUM gauge dict using the given device_id."""
    return {
        "gauge_id": f"{device_id}-g3",
        "number": 3,
        "kind": "analog",
        "gas": "VACUUM",
        "reading": VAC_READING,
        "unit": "mmHg",
        "status": "OK",
        "status_text": "within the safe range",
        "safe_low": VAC_SAFE_LOW,
        "safe_high": VAC_SAFE_HIGH,
        "safe_critical": VAC_SAFE_CRITICAL,
        "safe_buffer": VAC_SAFE_BUFFER,
        "confidence_pct": 95,
    }


def o2_gauge(device_id, reading, confidence_pct=96):
    status, status_text = o2_gauge_status(reading)
    return {
        "gauge_id": f"{device_id}-g1",
        "number": 1,
        "kind": "analog",
        "gas": "OXYGEN",
        "reading": reading,
        "unit": "kg/cm2",
        "status": status,
        "status_text": status_text,
        "safe_low": O2_SAFE_LOW,
        "safe_high": O2_SAFE_HIGH,
        "safe_critical": O2_SAFE_CRITICAL,
        "safe_buffer": O2_SAFE_BUFFER,
        "confidence_pct": confidence_pct,
    }


def o2_reasons(reading):
    status, _ = o2_gauge_status(reading)
    reasons = []
    if status == "CRITICAL":
        reasons.append(
            f"#1 OXYGEN needle reads {reading} kg/cm2 "
            f"(safe range {O2_SAFE_LOW}-{O2_SAFE_HIGH} kg/cm2) -> CRITICALLY LOW"
        )
        reasons.append("lit RED lamp (LOW / ALARM)")
    elif status == "LOW":
        reasons.append(
            f"#1 OXYGEN needle reads {reading} kg/cm2 "
            f"(safe range {O2_SAFE_LOW}-{O2_SAFE_HIGH} kg/cm2) -> LOW"
        )
    elif status == "NEAR_LOW":
        reasons.append(
            f"#1 OXYGEN needle reads {reading} kg/cm2 "
            f"(safe_low {O2_SAFE_LOW}, buffer {O2_SAFE_BUFFER}) -> NEAR LOW"
        )
    return reasons


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------

def now_ts():
    return datetime.now(IST).isoformat(timespec="seconds")


def ts_offset(seconds_delta):
    """Return an ISO timestamp offset by seconds_delta from now."""
    return (datetime.now(IST) + timedelta(seconds=seconds_delta)).isoformat(timespec="seconds")


def build_message(device_id, seq, event, o2_reading, timestamp=None,
                  unreadable=False, confidence_pct=97):
    """Build a full tablet-style message dict."""
    ts = timestamp or now_ts()

    if unreadable:
        return {
            "device_id": device_id,
            "timestamp": ts,
            "seq": seq,
            "event": event,
            "alert_status": "UNREADABLE",
            "confidence_pct": None,
            "reading": None,
            "unit": None,
            "gas": None,
            "gauges": [],
            "lamps": [],
            "reasons": ["camera could not read any gauge"],
            "app_version": "0.1.0",
        }

    o2  = o2_gauge(device_id, o2_reading, confidence_pct=confidence_pct - 1)
    vac = vac_gauge(device_id)
    alert   = o2_alert_status(o2["status"])
    lamps   = ["red"] if alert == "CRITICAL" else ["green"]
    reasons = o2_reasons(o2_reading) if alert == "CRITICAL" else []

    return {
        "device_id": device_id,
        "timestamp": ts,
        "seq": seq,
        "event": event,
        "alert_status": alert,
        "confidence_pct": confidence_pct,
        "reading": o2_reading,
        "unit": "kg/cm2",
        "gas": "OXYGEN",
        "gauges": [o2, vac],
        "lamps": lamps,
        "reasons": reasons,
        "app_version": "0.1.0",
    }


# ---------------------------------------------------------------------------
# HTTP sender
# ---------------------------------------------------------------------------

def send(url, payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            response_body = resp.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        response_body = exc.read().decode(errors="replace")
    except urllib.error.URLError as exc:
        print(f"  [CONNECTION ERROR] {exc.reason}")
        return

    # Pretty-print if JSON
    try:
        response_body = json.dumps(json.loads(response_body), indent=2)
    except (json.JSONDecodeError, ValueError):
        pass

    print(f"  → HTTP {status}")
    print(f"  → {response_body}")


def send_and_describe(url, payload, label=None):
    desc = label or (
        f"device={payload['device_id']} seq={payload['seq']} "
        f"event={payload['event']} alert_status={payload['alert_status']}"
    )
    print(f"\nSending: {desc}")
    print(json.dumps(payload, indent=2))
    send(url, payload)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def scenario_normal(device_id, url, _base_seq=None):
    msg = build_message(device_id, next_seq(device_id), "status_change", 4.5)
    send_and_describe(url, msg)


def scenario_critical(device_id, url, _base_seq=None):
    msg = build_message(device_id, next_seq(device_id), "status_change", 2.5)
    send_and_describe(url, msg)


def scenario_low(device_id, url, _base_seq=None):
    msg = build_message(device_id, next_seq(device_id), "status_change", 3.3)
    send_and_describe(url, msg)


def scenario_near_low(device_id, url, _base_seq=None):
    # 3.6 is inside safe range but within buffer (3.5 + 0.2 = 3.7)
    msg = build_message(device_id, next_seq(device_id), "status_change", 3.6)
    send_and_describe(url, msg)


def scenario_unreadable(device_id, url, _base_seq=None):
    msg = build_message(device_id, next_seq(device_id), "status_change", None, unreadable=True)
    send_and_describe(url, msg)


def scenario_heartbeat(device_id, url, _base_seq=None):
    msg = build_message(device_id, next_seq(device_id), "heartbeat", 4.5)
    send_and_describe(url, msg)


def scenario_duplicate(device_id, url, _base_seq=None):
    seq = next_seq(device_id)
    msg = build_message(device_id, seq, "status_change", 4.5)
    send_and_describe(url, msg, label=f"first send  seq={seq}")
    send_and_describe(url, msg, label=f"duplicate   seq={seq} (same message)")


def scenario_out_of_order(device_id, url, _base_seq=None):
    # Three messages 2 minutes apart; sent newest → oldest → middle
    seq0 = next_seq(device_id)
    seq1 = next_seq(device_id)
    seq2 = next_seq(device_id)
    newest = build_message(device_id, seq2, "status_change", 4.5, timestamp=ts_offset(0))
    oldest = build_message(device_id, seq0, "status_change", 4.3, timestamp=ts_offset(-240))
    middle = build_message(device_id, seq1, "status_change", 4.4, timestamp=ts_offset(-120))

    send_and_describe(url, newest, label="newest  (sent first)")
    send_and_describe(url, oldest, label="oldest  (sent second)")
    send_and_describe(url, middle, label="middle  (sent third)")


def scenario_sequence(device_id, url, _base_seq=None):
    steps = [
        (4.5, "normal"),
        (2.5, "critical"),
        (4.5, "back to normal"),
    ]
    for i, (reading, label) in enumerate(steps):
        if i > 0:
            print(f"\n  (sleeping 5 s…)")
            time.sleep(5)
        seq = next_seq(device_id)
        msg = build_message(device_id, seq, "status_change", reading, timestamp=now_ts())
        send_and_describe(url, msg, label=f"{label}  seq={seq}")


def scenario_multi(device_id, url, _base_seq=None):
    """
    Three-device demonstration:
      1. Send NORMAL for tab-01, tab-02, tab-03.
      2. Wait 5 s.
      3. Send CRITICAL for tab-02 only.
      4. Wait 5 s.
      5. Send NORMAL for tab-02 to clear the alert.

    The --device flag is ignored for this scenario because it drives
    all three devices explicitly.
    """
    devices = ["tab-01", "tab-02", "tab-03"]

    print("\n── Step 1: NORMAL for all three devices ──────────────────────")
    for dev in devices:
        seq = next_seq(dev)
        msg = build_message(dev, seq, "status_change", 4.5, timestamp=now_ts())
        send_and_describe(url, msg, label=f"NORMAL  device={dev}  seq={seq}")

    print(f"\n  (sleeping 5 s before CRITICAL…)")
    time.sleep(5)

    print("\n── Step 2: CRITICAL for tab-02 only ──────────────────────────")
    seq = next_seq("tab-02")
    msg = build_message("tab-02", seq, "status_change", 2.5, timestamp=now_ts())
    send_and_describe(url, msg, label=f"CRITICAL  device=tab-02  seq={seq}")

    print(f"\n  (sleeping 5 s before clearing…)")
    time.sleep(5)

    print("\n── Step 3: NORMAL for tab-02 (clears the alert) ──────────────")
    seq = next_seq("tab-02")
    msg = build_message("tab-02", seq, "status_change", 4.5, timestamp=now_ts())
    send_and_describe(url, msg, label=f"NORMAL  device=tab-02  seq={seq}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

SCENARIOS = {
    "normal":       scenario_normal,
    "critical":     scenario_critical,
    "low":          scenario_low,
    "near_low":     scenario_near_low,
    "unreadable":   scenario_unreadable,
    "heartbeat":    scenario_heartbeat,
    "duplicate":    scenario_duplicate,
    "out_of_order": scenario_out_of_order,
    "sequence":     scenario_sequence,
    "multi":        scenario_multi,
}


def main():
    parser = argparse.ArgumentParser(
        description="Post tablet-style messages to the Oxygen Flow Check Portal."
    )
    parser.add_argument("scenario", choices=list(SCENARIOS),
                        help="Which scenario to run")
    parser.add_argument("--device", default="tab-01",
                        help="device_id to use (default: tab-01); ignored by 'multi'")
    parser.add_argument("--url", default="http://localhost:8000/api/readings",
                        help="Portal endpoint (default: http://localhost:8000/api/readings)")
    args = parser.parse_args()

    print(f"Scenario : {args.scenario}")
    print(f"Device   : {args.device}{'  (ignored for multi)' if args.scenario == 'multi' else ''}")
    print(f"URL      : {args.url}")

    SCENARIOS[args.scenario](args.device, args.url)
    print("\nDone.")


if __name__ == "__main__":
    main()
