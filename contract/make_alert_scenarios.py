"""Generates contract/alert_scenarios.json - the SHARED test vectors that both the
Python reference engine and the Kotlin AlertEngine must pass.

Step fields: t (s), value (or null), conf, agree, lamp, battery, charging,
             tick (true = watchdog tick, no frame), expect (status), expect_trend.
Config = contract/monitor_config.default.json unless a scenario overrides.
"""
import json
from pathlib import Path


def frame(t, v, conf=0.95, agree=True, lamp="NORMAL", **kw):
    d = {"t": t, "value": v, "conf": conf, "agree": agree, "lamp": lamp}
    d.update(kw)
    return d


def series(t0, values, dt=1.0, **kw):
    return [frame(t0 + i * dt, v, **kw) for i, v in enumerate(values)]


S = []

# 1 steady
steps = series(0, [5.0] * 20)
for s in steps:
    s["expect"] = "OK"
S.append({"name": "steady_ok", "steps": steps})

# 2 one glare frame must not alarm
steps = series(0, [5.0] * 10 + [2.0] + [5.0] * 10)
for s in steps:
    s["expect"] = "OK"
S.append({"name": "single_glare_frame_no_alarm", "steps": steps})

# 3 two isolated low frames must not alarm either
steps = series(0, [5.0] * 6 + [3.0, 5.0, 3.0, 5.0] + [5.0] * 6)
for s in steps:
    s["expect"] = "OK"
S.append({"name": "isolated_low_frames_no_alarm", "steps": steps})

# 4 sudden drop to LOW: alarm on the 3rd consecutive low reading
steps = series(0, [5.0] * 6 + [3.2] * 6)
for i, s in enumerate(steps):
    s["expect"] = "OK" if i < 8 else "LOW"
S.append({"name": "sudden_drop_low_after_3", "steps": steps})

# 5 sudden drop to CRITICAL
steps = series(0, [5.0] * 6 + [2.0] * 6)
for i, s in enumerate(steps):
    s["expect"] = "OK" if i < 8 else "CRITICAL"
S.append({"name": "sudden_drop_critical_after_3", "steps": steps})

# 6 hysteresis: 3.6 is above LOW (3.5) but below LOW+hyst (3.7) -> stays LOW
vals = [5.0] * 5 + [3.2] * 5 + [3.6] * 8 + [4.0] * 6
steps = series(0, vals)
for i, s in enumerate(steps):
    if i < 7:
        s["expect"] = "OK"
    elif i < 18 + 4:
        s["expect"] = "LOW"
    else:
        s["expect"] = "OK"
S.append({"name": "hysteresis_clear", "steps": steps})

# 7 critical recovers to LOW then OK
vals = [5.0] * 5 + [2.0] * 5 + [3.4] * 6 + [4.5] * 6
steps = series(0, vals)
exp = ["OK"] * 7 + ["CRITICAL"] * 3 + ["CRITICAL"] * 4 + ["LOW"] * 2 + ["LOW"] * 4 + ["OK"] * 2
for s, e in zip(steps, exp):
    s["expect"] = e
S.append({"name": "critical_to_low_to_ok", "steps": steps})

# 8 trend: falls 1.2 kg/cm2 per minute while still above LOW
vals = [6.0 - 0.02 * i for i in range(61)]
steps = series(0, vals)
for s in steps:
    s["expect"] = "OK"
    if s["t"] >= 40:
        s["expect_trend"] = True
    if s["t"] < 29:
        s["expect_trend"] = False
S.append({"name": "falling_trend_warning", "steps": steps})

# 9 stable noisy reading: no trend
import math
vals = [5.0 + 0.05 * math.sin(i) for i in range(90)]
steps = series(0, vals)
for s in steps:
    s["expect"] = "OK"
    s["expect_trend"] = False
S.append({"name": "noise_no_trend", "steps": steps})

# 10 uncertain frames: UNCERTAIN on 3rd consecutive bad frame, OK again after a good one
steps = series(0, [5.0] * 5) + series(5, [5.0] * 4, conf=0.1) + series(9, [5.0] * 2)
exp = ["OK"] * 5 + ["OK", "OK", "UNCERTAIN", "UNCERTAIN"] + ["OK", "OK"]
for s, e in zip(steps, exp):
    s["expect"] = e
S.append({"name": "uncertain_after_3_bad", "steps": steps})

# 11 disagreement counts as bad
steps = series(0, [5.0] * 5) + series(5, [5.0] * 3, agree=False)
exp = ["OK"] * 5 + ["OK", "OK", "UNCERTAIN"]
for s, e in zip(steps, exp):
    s["expect"] = e
S.append({"name": "disagreement_uncertain", "steps": steps})

# 12 MONITORING_LOST after 30 s of unreadable frames
steps = series(0, [5.0] * 3) + series(3, [None] * 35, conf=0.0)
for s in steps:
    s["expect"] = "MONITORING_LOST" if s["t"] - 2 >= 30 else ("OK" if s["t"] < 5 else "UNCERTAIN")
S.append({"name": "monitoring_lost_unreadable", "steps": steps})

# 13 watchdog: frames stop arriving completely
steps = series(0, [5.0] * 3) + [{"t": 2 + k, "tick": True} for k in (5, 10, 20, 29.5, 30, 45)]
for s in steps:
    s["expect"] = "MONITORING_LOST" if s["t"] - 2 >= 30 else "OK"
S.append({"name": "monitoring_lost_no_frames", "steps": steps})

# 14 no valid reading ever since start
steps = [frame(t, None, conf=0.0) for t in range(0, 32)]
for s in steps:
    s["expect"] = "MONITORING_LOST" if s["t"] >= 30 else ("UNCERTAIN" if s["t"] >= 2 else "OK")
S.append({"name": "never_readable_from_start", "steps": steps})

# 15 panel LOW lamp overrides a needle that disagrees (alert-biased)
steps = series(0, [5.0] * 5) + series(5, [5.0] * 4, agree=False, lamp="LOW")
exp = ["OK"] * 5 + ["OK", "OK", "LOW", "LOW"]
for s, e in zip(steps, exp):
    s["expect"] = e
S.append({"name": "panel_lamp_low_raises_low", "steps": steps})

# 16 lamp OFF for 30 s (panel unpowered) -> MONITORING_LOST
steps = series(0, [5.0] * 3) + series(3, [5.0] * 32, lamp="OFF")
for s in steps:
    s["expect"] = "MONITORING_LOST" if s["t"] - 3 >= 30 else "OK"
S.append({"name": "lamp_off_lost", "steps": steps})

# 17 battery low and unplugged -> MONITORING_LOST, recovers when charging
steps = series(0, [5.0] * 3) + series(3, [5.0] * 2, battery=10, charging=False) + series(5, [5.0] * 2, battery=10, charging=True)
exp = ["OK"] * 3 + ["MONITORING_LOST"] * 2 + ["OK"] * 2
for s, e in zip(steps, exp):
    s["expect"] = e
S.append({"name": "battery_low_lost", "steps": steps})

# 18 alarm must NOT clear on bad data
steps = series(0, [5.0] * 5 + [3.0] * 5) + series(10, [None] * 10, conf=0.0)
for i, s in enumerate(steps):
    s["expect"] = "OK" if i < 7 else "LOW"
S.append({"name": "alarm_latched_through_bad_frames", "steps": steps})

# 19 slow leak: crosses LOW gradually -> alarm, trend first
vals = [4.5 - 0.01 * i for i in range(150)]          # 0.6 / min
steps = series(0, vals)
for s, v in zip(steps, vals):
    if v >= 3.5 + 0.03:
        s["expect"] = "OK"
    elif v < 3.5 - 0.04:
        s["expect"] = "LOW"
    if s["t"] >= 45 and v > 3.6:
        s["expect_trend"] = True
S.append({"name": "slow_leak_trend_then_low", "steps": steps})

out = {"config": "contract/monitor_config.default.json", "scenarios": S}
Path(__file__).with_name("alert_scenarios.json").write_text(json.dumps(out, indent=1))
print(len(S), "scenarios,", sum(len(s["steps"]) for s in S), "steps")
