"""Lamp reader: fixed boxes, HSV colour + brightness. No ML.

Thresholds are mirrored 1:1 in the Kotlin port (LampReader.kt) - change both.
OpenCV HSV ranges: H 0-179, S 0-255, V 0-255.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .calibration import Calibration

HUE_RANGES = {            # inclusive OpenCV hue ranges
    "red": [(0, 10), (160, 179)],
    "amber": [(11, 35)],
    "green": [(36, 95)],
}


@dataclass(frozen=True)
class LampParams:
    # a lit lamp is bright RELATIVE to the frame: min V = clamp(rel * median frame V, floor, cap)
    min_v_rel: float = 0.8
    min_v_floor: int = 60
    min_v_cap: int = 190
    min_s: int = 70             # ... and coloured
    white_v: int = 235          # saturated-to-white core of a very bright lamp
    white_max_s: int = 60
    lit_frac: float = 0.12      # coloured-bright fraction to call it lit
    lit_frac_with_core: float = 0.05
    core_frac: float = 0.15


def frame_median_v(img_bgr: np.ndarray) -> float:
    small = cv2.resize(img_bgr, (64, 48), interpolation=cv2.INTER_AREA)
    return float(np.median(cv2.cvtColor(small, cv2.COLOR_BGR2HSV)[..., 2]))


def min_v_for(frame_v: float, p: LampParams) -> float:
    return float(min(max(p.min_v_rel * frame_v, p.min_v_floor), p.min_v_cap))


def lamp_score(img_bgr: np.ndarray, box, hue: str, p: LampParams = LampParams(),
               frame_v: float | None = None) -> dict:
    if frame_v is None:
        frame_v = frame_median_v(img_bgr)
    min_v = min_v_for(frame_v, p)
    x, y, w, h = [int(v) for v in box]
    H, W = img_bgr.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return {"lit": False, "colored": 0.0, "core": 0.0, "valid": False}
    hsv = cv2.cvtColor(img_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    hh, ss, vv = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    in_hue = np.zeros(hh.shape, bool)
    for lo, hi in HUE_RANGES[hue]:
        in_hue |= (hh >= lo) & (hh <= hi)
    colored = float(np.mean(in_hue & (ss >= p.min_s) & (vv >= min_v)))
    core = float(np.mean((vv >= p.white_v) & (ss <= p.white_max_s)))
    lit = colored >= p.lit_frac or (colored >= p.lit_frac_with_core and core >= p.core_frac)
    return {"lit": bool(lit), "colored": round(colored, 3), "core": round(core, 3), "valid": True}


def read_lamps(img_bgr: np.ndarray, cal: Calibration, p: LampParams = LampParams()):
    """Return (lamp_state, per-lamp details).

    lamp_state: one lit lamp -> its name (NORMAL / LOW / HIGH);
                none lit -> OFF; several lit -> CONFLICT; no lamps calibrated -> UNKNOWN.
    """
    if not cal.lamps:
        return "UNKNOWN", {}
    fv = frame_median_v(img_bgr)
    details = {l.name: lamp_score(img_bgr, l.box, l.hue, p, fv) for l in cal.lamps}
    lit = [n for n, d in details.items() if d["lit"]]
    if len(lit) == 1:
        return lit[0], details
    return ("OFF" if not lit else "CONFLICT"), details
