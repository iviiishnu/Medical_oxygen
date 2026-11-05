import json
from pathlib import Path

import cv2
import jsonschema
import numpy as np
import pytest

from o2gauge.calibration import Calibration
from o2gauge.config import MonitorConfig
from o2gauge.fusion import fuse
from o2gauge.geometry import Scale, dial_angle, point_at, value_from_keypoints
from o2gauge.lamps import read_lamps
from o2gauge.pipeline import GaugePipeline
from o2gauge.stage_a import NeedleResult, read_needle
from o2gauge.synth import GAUGES, Layout, AugParams, augment, render_dial, render_scene, calibration_from_gt

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contract" / "reading.schema.json").read_text())


# ------------------------------------------------------------------ geometry
@pytest.mark.parametrize("px,py,ang", [(0, -1, 0), (1, 0, 90), (0, 1, 180), (-1, 0, 270)])
def test_dial_angle_cardinal(px, py, ang):
    assert dial_angle(0, 0, px, py) == pytest.approx(ang)


def test_point_at_roundtrip():
    for a in np.linspace(0, 359, 37):
        x, y = point_at(10, 20, a, 5)
        assert dial_angle(10, 20, x, y) == pytest.approx(a % 360, abs=1e-9)


def test_scale_cw_270():
    s = Scale(225, 135, 0, 16)
    assert s.sweep == pytest.approx(270)
    assert s.value(225)[0] == pytest.approx(0)
    assert s.value(0)[0] == pytest.approx(16 * 135 / 270)      # 12 o'clock = mid-scale
    assert s.value(135)[0] == pytest.approx(16)
    assert s.angle(8) == pytest.approx(0)


def test_scale_dead_zone_clamps():
    s = Scale(225, 135, 0, 16)
    v, ok = s.value(150)          # just past max
    assert (v, ok) == (16, False)
    v, ok = s.value(210)          # just below zero (needle on the stop pin)
    assert (v, ok) == (0, False)


def test_scale_ccw():
    s = Scale(135, 225, 0, 10, "ccw")
    assert s.sweep == pytest.approx(270)
    assert s.value(0)[0] == pytest.approx(5)
    assert s.value(225)[0] == pytest.approx(10)


def test_keypoints_to_value():
    c = (100, 100)
    z = point_at(*c, 225, 50)
    m = point_at(*c, 135, 50)
    tip = point_at(*c, 90, 40)                    # 3 o'clock
    v, ok = value_from_keypoints(c, tip, z, m, 0, 16)
    assert ok and v == pytest.approx(16 * 225 / 270)


# ----------------------------------------------------------------- fixtures
@pytest.fixture(scope="module", params=list(GAUGES))
def scene(request):
    spec = GAUGES[request.param]
    lay = Layout()
    dial = render_dial(spec, lay, np.random.default_rng(5))
    _, gt0 = render_scene(spec, 0, lay, dial_cache=dial)
    return spec, lay, dial, Calibration.from_dict(calibration_from_gt(gt0))


def test_stage_a_clean_accuracy(scene):
    spec, lay, dial, cal = scene
    for v in np.linspace(spec.min_value, spec.max_value, 41):
        img, _ = render_scene(spec, float(v), lay, dial_cache=dial)
        r = read_needle(img, cal)
        assert abs(r.value - v) <= 0.05 * spec.max_value / 16, (v, r)
        assert r.confidence >= 0.9


def test_stage_a_augmented_targets(scene):
    """Plan targets on (synthetic) augmented frames: confident readings must be accurate."""
    spec, lay, dial, cal = scene
    rng = np.random.default_rng(11)
    errs, unconf = [], 0
    for _ in range(120):
        v = float(rng.uniform(spec.min_value, spec.max_value))
        img, _ = render_scene(spec, v, lay, dial_cache=dial)
        img, _ = augment(img, {"lamps": [], "center": [0, 0], "tip": [0, 0], "zero": [0, 0], "max": [0, 0],
                               "radius": 1}, rng, AugParams())
        r = read_needle(img, cal)
        if r.confidence < MonitorConfig().min_confidence:
            unconf += 1
            continue
        errs.append(abs(r.value - v))
    errs = np.array(errs)
    assert errs.mean() <= 0.2 and errs.max() <= 0.5, (errs.mean(), errs.max())
    assert unconf <= 6


def test_blocked_camera_unreadable(scene):
    _, _, _, cal = scene
    for img in (np.zeros((480, 640, 3), np.uint8), np.full((480, 640, 3), 128, np.uint8)):
        r = read_needle(img, cal)
        assert r.value is None and r.confidence == 0


def test_perspective_rectification():
    spec, lay = GAUGES["alarm_box_16"], Layout()
    dial = render_dial(spec, lay, np.random.default_rng(2))
    # squash the frame vertically by 15% (camera looking from below/above)
    S = np.float32([[1, 0, 0], [0, 0.85, 36]])
    rim = [point_at(lay.cx, lay.cy, a, lay.radius * 1.02) for a in range(0, 360, 30)]
    def sq(p):
        return [float(p[0]), float(0.85 * p[1] + 36)]
    _, gt0 = render_scene(spec, 0, lay, dial_cache=dial)
    d = calibration_from_gt(gt0)
    d.update(center=sq(d["center"]), zero_point=sq(d["zero_point"]), max_point=sq(d["max_point"]),
             rim_points=[sq(p) for p in rim])
    cal = Calibration.from_dict(d)
    d_nofix = dict(d, rim_points=None)
    cal_nofix = Calibration.from_dict(d_nofix)
    worst_fix, worst_nofix = 0, 0
    for v in (1.0, 4.0, 7.3, 10.0, 14.5):
        img, _ = render_scene(spec, v, lay, dial_cache=dial)
        img = cv2.warpAffine(img, S, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REPLICATE)
        worst_fix = max(worst_fix, abs(read_needle(img, cal).value - v))
        worst_nofix = max(worst_nofix, abs(read_needle(img, cal_nofix).value - v))
    assert worst_fix < 0.1
    assert worst_fix < worst_nofix


def test_lamps(scene):
    spec, lay, dial, cal = scene
    for lit in list(spec.lamps) + [None]:
        img, _ = render_scene(spec, 5.0, lay, lit=lit, dial_cache=dial)
        state, _ = read_lamps(img, cal)
        assert state == (lit or "OFF")


def test_lamps_unknown_without_calibration(scene):
    spec, lay, dial, cal = scene
    d = cal.to_dict()
    d["lamps"] = []
    img, _ = render_scene(spec, 5.0, lay, dial_cache=dial)
    assert read_lamps(img, Calibration.from_dict(d))[0] == "UNKNOWN"


# ------------------------------------------------------------------- fusion
CFG = MonitorConfig()


def nr(v, c=0.9, m="stage_a"):
    return NeedleResult(v, 0, c, method=m)


def test_fusion_agree_ok():
    f = fuse(nr(5.4), nr(5.5, m="stage_b"), "NORMAL", CFG)
    assert f.status == "OK" and f.method_agree and f.value == 5.5 and f.confidence > 0.9


def test_fusion_disagree_uncertain():
    f = fuse(nr(5.4), nr(8.0, m="stage_b"), "NORMAL", CFG)
    assert f.status == "UNCERTAIN" and not f.method_agree


def test_fusion_lamp_contradiction():
    f = fuse(nr(6.0), None, "LOW", CFG)
    assert f.status == "UNCERTAIN" and not f.lamp_agree


def test_fusion_lamp_near_setpoint_tolerated():
    f = fuse(nr(3.7), None, "LOW", CFG)
    assert f.lamp_agree and f.status == "OK"


def test_fusion_levels():
    assert fuse(nr(3.2), None, "LOW", CFG).status == "LOW"
    assert fuse(nr(2.0), None, "LOW", CFG).status == "CRITICAL"


def test_fusion_nothing_readable():
    f = fuse(NeedleResult(None, None, 0.0), None, "OFF", CFG)
    assert f.status == "UNCERTAIN" and f.value is None


def test_fusion_falls_back_to_stage_a():
    f = fuse(nr(5.0), nr(9.0, c=0.1, m="stage_b"), "NORMAL", CFG)
    assert f.value == 5.0 and f.status == "OK"


# ---------------------------------------------------------- pipeline + schema
def test_pipeline_message_matches_schema(scene):
    spec, lay, dial, cal = scene
    pipe = GaugePipeline(cal, CFG)
    for v in (5.4, 3.2, 1.0):
        img, _ = render_scene(spec, v, lay, dial_cache=dial)
        msg, _ = pipe.read(img)
        jsonschema.validate(msg, SCHEMA)
    msg, _ = pipe.read(np.zeros((480, 640, 3), np.uint8))
    jsonschema.validate(msg, SCHEMA)
    assert msg["status"] == "UNCERTAIN" and msg["value"] is None


# --------------------------------------------------------------- calibration
def test_calibration_roundtrip(tmp_path, scene):
    _, _, _, cal = scene
    p = tmp_path / "c.json"
    cal.save(p)
    assert Calibration.load(p) == cal


@pytest.mark.parametrize("bad", [
    {"radius": 1},
    {"max_value": -1},
    {"zero_point": [250, 241]},
    {"direction": "up"},
    {"lamps": [{"name": "LOW", "box": [0, 0, 0, 5], "hue": "red"}]},
    {"bogus_key": 1},
])
def test_calibration_rejects_bad(bad, scene):
    _, _, _, cal = scene
    d = cal.to_dict()
    d.update(bad)
    with pytest.raises((ValueError, TypeError)):
        Calibration.from_dict(d)
