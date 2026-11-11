"""Regression tests for bugs found on 11 Nov 2026 (general model + panel specialist)."""
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vision/tools"))
GEN = ROOT / "vision/models/gauge_pose.onnx"
PANEL = ROOT / "vision/models/gauge_pose_panel.onnx"
needs = pytest.mark.skipif(not (GEN.exists() and PANEL.exists()), reason="models not present")


@pytest.fixture(scope="module")
def reader():
    from o2gauge.auto import AutoReader
    from o2gauge.stage_b import KeypointReader
    return AutoReader(KeypointReader(GEN), panel_model=KeypointReader(PANEL))


@needs
def test_red_lamp_is_never_taken_for_a_dial(reader):
    """needle high (11.2) but the alarm lamp lit RED: must be ABNORMAL (was NORMAL 99 %: the general model
    found the round lit lamp as 'dial #2', and lamps on a dial are ignored)."""
    from eval_auto import full_with_value, set_lamps
    from o2gauge.photo_synth import load_photo_dial
    d = load_photo_dial(ROOT / "samples/real/alarm_box")
    img = set_lamps(full_with_value("alarm_box", d, 11.2), "red")
    r = reader.read(img)
    assert "red" in [l.color for l in r["lamps"]]
    assert r["verdict"].verdict == "ABNORMAL"


@needs
def test_printed_label_is_not_a_digital_display_on_a_small_panel(reader):
    """alarm box at half size: the printed LOW / NORMAL labels must not become the main 'digital' reading."""
    img = cv2.imread(str(ROOT / "samples/real/alarm_box.jpg"))
    sm = cv2.resize(img, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    sm = cv2.copyMakeBorder(sm, 300, 300, 400, 400, cv2.BORDER_CONSTANT, value=(150, 150, 150))
    r = reader.read(sm)
    assert r["main"] is not None and r["main"].kind == "analog" and r["main"].gauge_type == "alarm_box"
    assert all(g.kind == "analog" for g in r["readings"])


@needs
def test_real_panels_match_eye_readings(reader):
    r = reader.read(cv2.imread(str(ROOT / "samples/real/magnate.jpg")))
    got = {g.gas: g.value for g in r["readings"]}
    assert abs(got["OXYGEN"] - 4.8) <= 0.15 and abs(got["MEDICAL AIR"] - 4.2) <= 0.15
    assert abs(got["VACUUM"] - 575) <= 20
    r = reader.read(cv2.imread(str(ROOT / "samples/real/alarm_box.jpg")))
    assert abs(r["main"].value - 5.05) <= 0.15
