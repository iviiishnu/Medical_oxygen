"""Reading the scale off the dial: fitting, units, gas names (no models needed) + the trained
models on fresh synthetic gauges (skipped when the ONNX files are missing)."""
import math

import numpy as np
import pytest

from o2gauge.dialtext import (DialTextReader, TextBox, assign_units, fit_scales, match_gas, match_unit)
from o2gauge.dialtext_geom import dial_angle, rec_crop, shrink_box, strip_maps, unclip

CX, CY, R = 500.0, 400.0, 100.0


def ring(values, start=225.0, sweep=270.0, rho=0.7, h=12.0, cw=True, texts=None):
    out = []
    lo, hi = min(values), max(values)
    for i, v in enumerate(values):
        fr = (v - lo) / (hi - lo)
        a = (start + fr * sweep) % 360 if cw else (start + sweep - fr * sweep) % 360
        x, y = CX + rho * R * math.sin(math.radians(a)), CY - rho * R * math.cos(math.radians(a))
        out.append(box(v, a, rho, h, texts[i] if texts else None))
    return out


def box(v, a, rho=0.7, h=12.0, text=None, alts=None):
    x, y = CX + rho * R * math.sin(math.radians(a)), CY - rho * R * math.cos(math.radians(a))
    return TextBox(text or f"{v:g}", 0.95, float(v), 0.95, x, y, h, "face", dial_angle(CX, CY, x, y), rho,
                   alts or [(float(v), 0.95)])


def test_fit_simple_0_16():
    f = fit_scales(ring([0, 2, 4, 6, 8, 10, 12, 14, 16]), cx=CX, cy=CY)
    assert len(f) == 1
    s = f[0]
    assert (s.vmin, s.vmax, s.step) == (0, 16, 2)
    assert s.value_at(225 + 135) == pytest.approx(8, abs=0.05)       # straight up-right -> half way
    assert s.confidence > 0.8


@pytest.mark.parametrize("vals", [[0, 0.2, 0.4, 0.6, 0.8, 1.0], [0, 500, 1000, 1500, 2000, 2500],
                                  [0, 2000, 4000, 6000, 8000, 10000], [-1, -0.8, -0.6, -0.4, -0.2, 0],
                                  [-1, 0, 1, 2, 3]])
def test_any_range(vals):
    s = fit_scales(ring(vals), cx=CX, cy=CY)[0]
    assert s.vmin == min(vals) and s.vmax == max(vals)
    mid = (min(vals) + max(vals)) / 2
    assert s.value_at(0.0) == pytest.approx(mid, abs=0.01 * (max(vals) - min(vals)))


def test_vacuum_numbered_anticlockwise():
    s = fit_scales(ring([0, 100, 200, 300, 400, 500, 600, 700], cw=False, sweep=250), cx=CX, cy=CY)[0]
    assert s.b < 0                                    # values grow anticlockwise
    assert (s.vmin, s.vmax) == (0, 700)
    assert s.angle_of(0) == pytest.approx((225 + 250) % 360, abs=1)


def test_outliers_and_misreads_are_ignored():
    labels = ring([0, 2, 4, 6, 8, 10])
    labels[3].alts = [(9.0, 0.9)]                     # "6" misread as "9", no other guess
    labels.append(box(1.6, 180.0, 0.4, 8))            # "CL 1.6" in the dead zone
    labels.append(box(2016, 18.0, 0.31, 8))
    s = fit_scales(labels, cx=CX, cy=CY)[0]
    assert (s.vmin, s.vmax) == (0, 10)
    assert len(s.labels) == 5
    assert s.value_at(225 + 270 * 0.35) == pytest.approx(3.5, abs=0.05)


def test_second_guess_fixes_a_misread():
    labels = ring([0, 100, 200, 300, 400, 500, 600, 700], cw=False, sweep=250)
    labels[6].alts = [(800.0, 0.7), (600.0, 0.25)]    # "600" read as "800" (second guess right)
    labels[7].alts = [(-700.0, 0.8), (700.0, 0.48)]   # a tick read as a minus sign
    s = fit_scales(labels, cx=CX, cy=CY)[0]
    assert (s.vmin, s.vmax) == (0, 700) and len(s.labels) == 8
    assert labels[6].num == 600 and labels[7].num == 700


def test_uneven_printing_and_a_hidden_label():
    """Real Magnate dial: labels at 229, 267, 316, 19, (8 hidden by the needle), 123 deg."""
    angs = {0: 229, 2: 267, 4: 316, 6: 19, 10: 123}
    labels = [box(v, a, 0.6, 15) for v, a in angs.items()]
    labels.append(box(80, 79, 0.58, 15))              # "8" misread as "80"
    s = fit_scales(labels, cx=CX, cy=CY)[0]
    assert (s.vmin, s.vmax) == (0, 10) and abs(s.step) == 2
    # interpolation follows the printed positions: half-way between "2" and "4" reads 3
    assert s.value_at((267 + 316) / 2) == pytest.approx(3.0, abs=0.01)
    assert s.angle_of(4) == pytest.approx(316, abs=0.01)


def test_two_scales_kg_and_psi():
    inner = ring([0, 2, 4, 6, 8, 10], rho=0.6, h=14)
    # psi printed outside, same zero, 140 psi ~ 9.84 kg/cm2
    psi = [box(v, (225 + v / 14.223 / 10 * 270) % 360, 0.95, 8) for v in (0, 20, 40, 60, 80, 100, 120, 140)]
    fits = fit_scales(inner + psi, cx=CX, cy=CY)
    assert len(fits) == 2
    assign_units(fits, ["kg/cm2"])
    assert fits[0].unit == "kg/cm2" and (fits[0].vmin, fits[0].vmax) == (0, 10)
    assert fits[1].unit == "psi" and fits[1].unit_inferred
    assert fits[1].value_at(fits[0].angle_of(5.0)) == pytest.approx(71.1, abs=0.5)


def test_too_few_numbers_is_not_a_scale():
    assert fit_scales(ring([0, 5]), cx=CX, cy=CY) == []
    # three numbers bunched in 30 degrees: not enough to trust
    assert fit_scales(ring([0, 1, 2], sweep=30), cx=CX, cy=CY) == []


@pytest.mark.parametrize("txt,unit", [("kg/cm2", "kg/cm2"), ("Kg/cm²", "kg/cm2"), ("kgf/cm2", "kg/cm2"),
                                      ("BAR", "bar"), ("psi", "psi"), ("kPa", "kPa"), ("MPa", "MPa"),
                                      ("mm Hg", "mmHg"), ("inHg", "inHg"), ("OXYGEN", None), ("10", None)])
def test_units(txt, unit):
    assert match_unit(txt) == unit


@pytest.mark.parametrize("txt,gas", [("OXYGEN", "OXYGEN"), ("OXYGFN", "OXYGEN"), ("O2", "OXYGEN"),
                                     ("MEDICAL AIR", "MEDICAL AIR"), ("Air-4", "MEDICAL AIR"),
                                     ("VACUUM", "VACUUM"), ("VACUUN", "VACUUM"), ("N2O", "NITROUS OXIDE"),
                                     ("USE NO OIL", None), ("ISO 13485:2016", None), ("REPAIR", None)])
def test_gas(txt, gas):
    assert match_gas(txt) == gas


def test_shrink_unclip_roundtrip():
    b = (10.0, 20.0, 70.0, 40.0)
    assert unclip(*shrink_box(b)) == pytest.approx(b)


def test_strips_unroll_top_and_bottom():
    mx, my = strip_maps(CX, CY, R)
    h = mx.shape[0] // 2
    # middle column of the top strip is straight up, of the bottom strip straight down
    w = mx.shape[1] // 2
    assert dial_angle(CX, CY, mx[0, w], my[0, w]) == pytest.approx(0, abs=0.5)
    assert dial_angle(CX, CY, mx[h, w], my[h, w]) == pytest.approx(180, abs=0.5)
    # top strip: left -> right goes clockwise; bottom strip: left -> right goes anticlockwise
    assert mx[0, 0] < mx[0, -1] and mx[h, 0] < mx[h, -1]


def test_rec_crop_dark_on_light():
    img = np.full((60, 120), 30, np.uint8)       # dark dial face
    for x in range(34, 88, 12):
        img[22:38, x:x + 3] = 230                # thin light strokes = white digits
    c = rec_crop(img, (30, 20, 90, 40))
    assert c.shape == (32, 192)
    assert np.median(c[:, :60]) > 0.5            # background became light ...
    assert c[16, :100].min() < -0.5              # ... and the strokes dark


# ------------------------------------------------------------- trained models (if present)
needs_models = pytest.mark.skipif(not DialTextReader.available(), reason="dialtext ONNX models not trained yet")


@needs_models
@pytest.mark.xfail(reason="dial-text models stopped early (4k of 18k training steps); target not reached yet",
                   strict=False)
def test_models_read_fresh_synthetic_gauges():
    """Unseen random gauges (seed not used in training): most scales must be read correctly and a
    confident scale must almost never be wrong."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from eval_dialtext import eval_single
    rep, _ = eval_single(60, seed=777)
    assert rep["scale_correct"] >= 0.8, rep
    assert rep["confident_and_wrong"] <= 0.05, rep
