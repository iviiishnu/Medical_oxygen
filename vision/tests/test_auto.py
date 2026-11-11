"""Automatic (no-calibration) reader: dial finding, gauge recognition, lamps, verdict."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from o2gauge.auto import AutoReader, Dial, GaugeReading, LitLamp, Verdict, decide, find_lit_lamps
from o2gauge.config import MonitorConfig

ROOT = Path(__file__).resolve().parents[2]
ONNX = ROOT / "vision/models/gauge_pose.onnx"
REAL = ROOT / "samples/real"
CFG = MonitorConfig()
needs_model = pytest.mark.skipif(not ONNX.exists(), reason="trained model not present")


@pytest.fixture(scope="module")
def reader():
    from o2gauge.stage_b import KeypointReader
    return AutoReader(KeypointReader(ONNX), CFG)


# ------------------------------------------------------------------ real photos, nothing given
@needs_model
# magnate: the arc ends at 150 psi = 10.55 kg/cm2 (not 10) and the photo is taken from below-left;
# read by eye on the psi scale the oxygen needle is at ~67-68 psi = ~4.75 kg/cm2
@pytest.mark.parametrize("stem,truth,n_lamps", [("alarm_box", 5.01, 1), ("magnate", 4.75, 4)])
def test_real_photo_fully_automatic(reader, stem, truth, n_lamps):
    r = reader.read(cv2.imread(str(REAL / f"{stem}.jpg")))
    m = r["main"]
    assert m.gauge_type == stem                       # scale recognised, not guessed
    assert abs(m.value - truth) <= 0.2
    assert r["verdict"].verdict == "NORMAL" and r["verdict"].confidence >= 0.9
    assert [l.color for l in r["lamps"]] == ["green"] * n_lamps


@needs_model
def test_magnate_finds_all_three_dials_and_oxygen_is_main(reader):
    r = reader.read(cv2.imread(str(REAL / "magnate.jpg")))
    assert len(r["readings"]) == 3
    assert abs(r["main"].dial.center[0] - 722) < 15 and abs(r["main"].dial.center[1] - 388) < 15


@needs_model
def test_blank_frame_cant_tell(reader):
    r = reader.read(np.full((720, 1280, 3), 128, np.uint8))
    assert r["main"] is None and r["verdict"].verdict == "CAN'T TELL" and r["verdict"].confidence == 0


@needs_model
@pytest.mark.parametrize("stem,value,lamp,expect", [
    ("alarm_box", 2.4, "red", "ABNORMAL"),
    ("alarm_box", 9.0, "green", "NORMAL"),
    ("magnate", 1.8, "red", "ABNORMAL"),
    ("magnate", 6.5, "red", "ABNORMAL"),           # conflict -> flagged, low confidence
    ("alarm_box", 3.0, "off", "ABNORMAL"),         # lamps off -> needle alone
])
def test_moved_needle_and_lamps(reader, stem, value, lamp, expect):
    import sys
    sys.path.insert(0, str(ROOT / "vision/tools"))
    from eval_auto import full_with_value, set_lamps
    from o2gauge.photo_synth import load_photo_dial
    img = set_lamps(full_with_value(stem, load_photo_dial(REAL / stem), value), lamp)
    r = reader.read(img)
    assert r["verdict"].verdict == expect
    assert abs(r["main"].value - value) <= 0.25
    if lamp == "red" and value >= CFG.low_threshold:
        assert r["verdict"].confidence <= 0.6         # disagreement is not reported as certain


# ------------------------------------------------------------------ lamps (no model needed)
def _lamp_scene(color_bgr, core=True):
    img = np.full((600, 800, 3), (200, 200, 200), np.uint8)
    cv2.circle(img, (600, 300), 45, color_bgr, -1)
    if core:
        cv2.circle(img, (600, 300), 22, (255, 255, 255), -1)       # blown-out centre
    cv2.putText(img, "LOW", (80, 300), cv2.FONT_HERSHEY_SIMPLEX, 3, (40, 40, 200), 8)   # printed red text
    return img


@pytest.mark.parametrize("bgr,color", [((0, 255, 40), "green"), ((20, 20, 255), "red"), ((0, 170, 255), "amber")])
def test_lit_lamp_colour_and_one_blob(bgr, color):
    lamps = find_lit_lamps(_lamp_scene(bgr))
    assert [l.color for l in lamps] == [color]


def test_unlit_lamp_and_print_ignored():
    img = _lamp_scene((30, 30, 110), core=False)                  # dark red = unlit lamp
    assert find_lit_lamps(img) == []


# ------------------------------------------------------------------ verdict rules (no model needed)
def _g(value, conf=0.95, known=True):
    d = Dial((0, 0), 10, 0.9, np.zeros((4, 3)))
    return GaugeReading(value, conf, value, value, "OK", d, None, [], "x" if known else None, "0-16", known)


def _l(color):
    return LitLamp(color, (0, 0, 10, 10), 100, 1.0)


def test_verdict_rules():
    assert decide(_g(5.0), [_l("green")], CFG).verdict == "NORMAL"
    assert decide(_g(2.0), [_l("red")], CFG).verdict == "ABNORMAL"
    assert decide(_g(5.0), [_l("red")], CFG).verdict == "ABNORMAL"          # safety: red lamp wins
    assert decide(_g(2.0), [_l("green")], CFG).verdict == "ABNORMAL"        # safety: low needle wins
    assert decide(None, [], CFG).verdict == "CAN'T TELL"
    assert decide(None, [_l("amber")], CFG).verdict == "ABNORMAL"


def test_confidence_behaviour():
    agree = decide(_g(6.0), [_l("green")], CFG).confidence
    needle_only = decide(_g(6.0), [], CFG).confidence
    conflict = decide(_g(6.0), [_l("red")], CFG).confidence
    near_limit = decide(_g(3.6), [], CFG).confidence
    unknown = decide(_g(6.0, known=False), [], CFG).confidence
    assert agree > needle_only > conflict
    assert near_limit < needle_only                   # close to the limit = less sure
    assert unknown < needle_only                      # scale guessed = less sure
    assert Verdict("NORMAL", 1.7, []).confidence == 0.99
