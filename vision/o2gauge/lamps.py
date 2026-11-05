"""Lamp reader: fixed boxes, HSV colour + brightness. No ML. Port-exact (LampReader.kt).

A lamp is LIT when enough of its box is bright AND of the lamp's own hue, where
"bright" is relative to the whole frame (min V = clamp(0.8 * median frame V, 60, 190)).
A very bright lamp often saturates to a white core, so a smaller coloured fraction
plus a white core also counts.

Neighbour glow (e.g. the Magnate column where the lit NORMAL lamp bleeds green onto
the unlit HIGH/LOW windows) is handled by `relative_margin`: when one lamp is
clearly stronger than the others, only that lamp is reported.
OpenCV HSV ranges: H 0-179, S 0-255, V 0-255.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .calibration import Calibration
from .imgops import hsv, grid_sample

HUE_RANGES = {            # inclusive OpenCV hue ranges
    "red": [(0, 10), (160, 179)],
    "amber": [(11, 35)],
    "green": [(36, 95)],
}


@dataclass(frozen=True)
class LampParams:
    min_v_rel: float = 0.8
    min_v_floor: int = 60
    min_v_cap: int = 190
    min_s: int = 70
    white_v: int = 235          # saturated-to-white core of a very bright lamp
    white_max_s: int = 60
    lit_frac: float = 0.12      # coloured-bright fraction to call it lit
    lit_frac_with_core: float = 0.05
    core_frac: float = 0.15
    halo_frac: float = 0.10     # coloured fraction of the ring around a blown-out core
    relative_margin: float = 3.0  # several "lit": keep the strongest if it beats the next by this factor


def frame_median_v(img_bgr: np.ndarray) -> float:
    _, _, v = hsv(grid_sample(img_bgr, 64))
    return float(np.median(v))


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
        return {"lit": False, "colored": 0.0, "core": 0.0, "halo": 0.0, "score": 0.0, "valid": False}
    hh, ss, vv = hsv(img_bgr[y0:y1, x0:x1])
    in_hue = np.zeros(hh.shape, bool)
    for lo, hi in HUE_RANGES[hue]:
        in_hue |= (hh >= lo) & (hh <= hi)
    colored = float(np.mean(in_hue & (ss >= p.min_s) & (vv >= min_v)))
    core = float(np.mean((vv >= p.white_v) & (ss <= p.white_max_s)))
    # a very bright lamp blows out to white; its colour is then only in the glow around it
    halo = 0.0
    if core >= p.core_frac:
        hx0, hy0 = max(0, x - w // 2), max(0, y - h // 2)
        hx1, hy1 = min(W, x + w + w // 2), min(H, y + h + h // 2)
        hh2, ss2, vv2 = hsv(img_bgr[hy0:hy1, hx0:hx1])
        inside = np.zeros(hh2.shape, bool)
        inside[y0 - hy0:y1 - hy0, x0 - hx0:x1 - hx0] = True
        hue2 = np.zeros(hh2.shape, bool)
        for lo, hi in HUE_RANGES[hue]:
            hue2 |= (hh2 >= lo) & (hh2 <= hi)
        ring = ~inside
        if ring.any():
            halo = float(np.mean((hue2 & (ss2 >= p.min_s) & (vv2 >= min_v))[ring]))
    lit = (colored >= p.lit_frac
           or (colored >= p.lit_frac_with_core and core >= p.core_frac)
           or (core >= p.core_frac and halo >= p.halo_frac))
    return {"lit": bool(lit), "colored": round(colored, 4), "core": round(core, 4), "halo": round(halo, 4),
            "score": round(colored + core + halo, 4), "valid": True}


def combine(details: dict, p: LampParams = LampParams()) -> str:
    lit = [n for n, d in details.items() if d["lit"]]
    if len(lit) == 1:
        return lit[0]
    if not lit:
        return "OFF"
    ranked = sorted(lit, key=lambda n: details[n]["score"], reverse=True)
    best, second = details[ranked[0]]["score"], details[ranked[1]]["score"]
    if best >= p.relative_margin * max(second, 1e-6):
        return ranked[0]
    return "CONFLICT"


def read_lamps(img_bgr: np.ndarray, cal: Calibration, p: LampParams = LampParams()):
    """Return (lamp_state, per-lamp details).

    lamp_state: one lit lamp -> its name (NORMAL / LOW / HIGH);
                none lit -> OFF; several equally lit -> CONFLICT; no lamps calibrated -> UNKNOWN.
    """
    if not cal.lamps:
        return "UNKNOWN", {}
    fv = frame_median_v(img_bgr)
    details = {l.name: lamp_score(img_bgr, l.box, l.hue, p, fv) for l in cal.lamps}
    return combine(details, p), details
