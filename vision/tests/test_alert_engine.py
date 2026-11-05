import json
from pathlib import Path

import pytest

from o2gauge.alert_engine import AlertEngine, EngineInput
from o2gauge.config import MonitorConfig

ROOT = Path(__file__).resolve().parents[2]
SCEN = json.loads((ROOT / "contract" / "alert_scenarios.json").read_text())["scenarios"]


def run_steps(steps, cfg=None):
    eng = AlertEngine(cfg or MonitorConfig.load())
    outs = []
    for s in steps:
        if s.get("tick"):
            out = eng.tick(s["t"])
        else:
            out = eng.update(EngineInput(ts=s["t"], value=s["value"], confidence=s["conf"],
                                         method_agree=s["agree"], lamp_state=s["lamp"],
                                         battery_pct=s.get("battery"), charging=s.get("charging", True)))
        outs.append(out)
    return outs


@pytest.mark.parametrize("sc", SCEN, ids=[s["name"] for s in SCEN])
def test_shared_scenarios(sc):
    outs = run_steps(sc["steps"])
    for i, (s, o) in enumerate(zip(sc["steps"], outs)):
        if "expect" in s:
            assert o.status == s["expect"], f"step {i} t={s['t']}: got {o.status}, want {s['expect']}"
        if "expect_trend" in s:
            assert o.trend_falling == s["expect_trend"], f"step {i} t={s['t']}: trend {o.trend_falling}"


def test_events_emitted_once_per_transition():
    sc = next(s for s in SCEN if s["name"] == "sudden_drop_low_after_3")
    outs = run_steps(sc["steps"])
    evs = [e for o in outs for e in o.events]
    assert evs == [{"type": "STATUS", "from": "OK", "to": "LOW", "ts": 8.0}]


def test_recovery_after_lost_uses_fresh_window():
    cfg = MonitorConfig.load()
    eng = AlertEngine(cfg)
    for t in range(5):
        eng.update(EngineInput(t, 2.0, 0.9, True))          # CRITICAL
    assert eng.update(EngineInput(5, 2.0, 0.9, True)).status == "CRITICAL"
    out = eng.tick(40)
    assert out.status == "MONITORING_LOST"
    out = eng.update(EngineInput(41, 6.0, 0.9, True))
    assert out.value == 6.0                                   # stale 2.0s discarded
    assert out.alarm == "CRITICAL"                            # but alarm still latched


def test_config_validation():
    with pytest.raises(ValueError):
        MonitorConfig(low_threshold=3.0, critical_threshold=3.5).validate()
