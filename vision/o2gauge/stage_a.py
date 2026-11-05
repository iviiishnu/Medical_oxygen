"""Stage A - classical needle reader (no training).

1. (optional) rectify perspective: the tapped rim ellipse is warped to a circle
2. build a "needle-ness" map (dark pixels, or red pixels for red needles),
   with CLAHE so glare and shadows matter less
3. sample it on polar rays around the dial centre (720 rays = 0.5 deg),
   only inside a radial band that contains the needle but not the tick marks
   or the needle tail
4. per ring, subtract that ring's median (removes printed coloured arcs)
5. per ray, take the median over the band -> a ray must be dark along most
   of its length, which numbers and text are not
6. smoothed circular profile -> peak = needle angle (sub-degree interpolation)
7. confidence from how much the peak stands out and how unique it is
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from .calibration import Calibration, apply_affine
from .geometry import Scale, dial_angle

N_RAYS = 720          # 0.5 degree resolution
N_RINGS = 48


@dataclass
class NeedleResult:
    value: float | None
    angle: float | None
    confidence: float
    in_range: bool = True
    method: str = "stage_a"
    reason: str = ""
    debug: dict = field(default_factory=dict)


def frame_quality(img: np.ndarray) -> tuple[bool, str]:
    """Reject frames where the gauge cannot possibly be read (blocked / black / blown out)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    small = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
    mean, std = float(small.mean()), float(small.std())
    if mean < 25:
        return False, "frame_too_dark"
    if mean > 245 and std < 8:
        return False, "frame_blown_out"
    if std < 6:
        return False, "frame_uniform_camera_blocked"
    return True, ""


def needle_map(img: np.ndarray, color: str) -> np.ndarray:
    """float32 map in [0,1]; high = looks like needle."""
    if color == "red":
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        red = ((h <= 10) | (h >= 165)).astype(np.float32)
        return red * (s.astype(np.float32) / 255.0) * np.clip(v.astype(np.float32) / 120.0, 0, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    g = clahe.apply(gray)
    return (255.0 - g.astype(np.float32)) / 255.0


def _rectified_geometry(img: np.ndarray, cal: Calibration):
    """Image, centre, scale and radius in the (perspective-corrected) frame."""
    rect = cal.rectification()
    if rect is None:
        return img, cal.center, cal.scale(), cal.radius
    M, rim_radius = rect
    h, w = img.shape[:2]
    out = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    c = apply_affine(M, cal.center)
    z = apply_affine(M, cal.zero_point)
    m = apply_affine(M, cal.max_point)
    scale = Scale(dial_angle(c[0], c[1], *z), dial_angle(c[0], c[1], *m),
                  cal.min_value, cal.max_value, cal.direction)
    return out, c, scale, rim_radius


def polar_profile(nmap: np.ndarray, cx: float, cy: float, radius: float,
                  r_in: float, r_out: float) -> np.ndarray:
    thetas = np.arange(N_RAYS, dtype=np.float32) * (360.0 / N_RAYS)
    radii = np.linspace(r_in * radius, r_out * radius, N_RINGS, dtype=np.float32)
    t = np.radians(thetas)[:, None]
    map_x = (cx + radii[None, :] * np.sin(t)).astype(np.float32)
    map_y = (cy - radii[None, :] * np.cos(t)).astype(np.float32)
    polar = cv2.remap(nmap, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                      borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    polar = polar - np.median(polar, axis=0, keepdims=True)    # per-ring background
    return np.median(polar, axis=1)                             # per-ray, robust to text


def _circular_smooth(p: np.ndarray, sigma_bins: float = 2.0) -> np.ndarray:
    k = int(math.ceil(sigma_bins * 3))
    x = np.arange(-k, k + 1)
    ker = np.exp(-0.5 * (x / sigma_bins) ** 2)
    ker /= ker.sum()
    padded = np.concatenate([p[-k:], p, p[:k]])
    return np.convolve(padded, ker, mode="valid")


def find_peak(profile: np.ndarray) -> tuple[float, float]:
    """Return (angle_deg, confidence) of the needle in a polar profile."""
    sm = _circular_smooth(profile)
    j = int(np.argmax(sm))
    y0, y1, y2 = sm[j - 1], sm[j], sm[(j + 1) % N_RAYS]
    denom = y0 - 2 * y1 + y2
    off = 0.5 * (y0 - y2) / denom if abs(denom) > 1e-12 else 0.0
    off = float(np.clip(off, -0.5, 0.5))
    angle = ((j + off) * 360.0 / N_RAYS) % 360.0

    med = float(np.median(sm))
    mad = float(np.median(np.abs(sm - med))) * 1.4826 + 1e-4
    peak = float(sm[j]) - med
    z = peak / mad
    excl = 12 * N_RAYS // 360                       # ignore +-12 deg around the peak
    idx = (np.arange(-excl, excl + 1) + j) % N_RAYS
    rest = sm.copy()
    rest[idx] = -np.inf
    second = float(rest.max()) - med
    uniqueness = 1.0 - max(second, 0.0) / peak if peak > 0 else 0.0
    conf_z = float(np.clip((z - 4.0) / 8.0, 0.0, 1.0))
    conf_sep = float(np.clip(uniqueness * 2.0, 0.0, 1.0))
    conf_abs = float(np.clip(peak / 0.12, 0.0, 1.0))       # needle must be clearly darker
    return angle, conf_z * conf_sep * conf_abs


def read_needle(img: np.ndarray, cal: Calibration) -> NeedleResult:
    ok, why = frame_quality(img)
    if not ok:
        return NeedleResult(None, None, 0.0, False, reason=why)
    rimg, c, scale, radius = _rectified_geometry(img, cal)
    nmap = needle_map(rimg, cal.needle_color)
    prof = polar_profile(nmap, c[0], c[1], radius, cal.needle_r_inner, cal.needle_r_outer)
    angle, conf = find_peak(prof)
    value, in_range = scale.value(angle)
    if not in_range:
        conf *= 0.5                      # needle in the dead zone is suspicious
    return NeedleResult(round(value, 3), round(angle, 2), round(conf, 3), in_range,
                        reason="" if conf > 0 else "no_needle_peak",
                        debug={"center": c, "radius": radius})


def draw_debug(img: np.ndarray, cal: Calibration, res: NeedleResult,
               lamp_states: dict | None = None) -> np.ndarray:
    out = img.copy()
    cx, cy = cal.center
    r = cal.radius
    cv2.circle(out, (int(cx), int(cy)), int(r), (255, 200, 0), 1, cv2.LINE_AA)
    for f in (cal.needle_r_inner, cal.needle_r_outer):
        cv2.circle(out, (int(cx), int(cy)), int(r * f), (200, 200, 200), 1, cv2.LINE_AA)
    for p, col in ((cal.zero_point, (0, 200, 0)), (cal.max_point, (0, 0, 255))):
        cv2.circle(out, (int(p[0]), int(p[1])), 5, col, -1, cv2.LINE_AA)
    if res.angle is not None:
        t = math.radians(res.angle)
        tip = (int(cx + r * 0.95 * math.sin(t)), int(cy - r * 0.95 * math.cos(t)))
        cv2.line(out, (int(cx), int(cy)), tip, (255, 0, 255), 2, cv2.LINE_AA)
    txt = (f"{res.value:.2f} {cal.unit}  conf {res.confidence:.2f}" if res.value is not None
           else f"UNREADABLE ({res.reason})")
    cv2.putText(out, txt, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(out, txt, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    for lamp in cal.lamps:
        x, y, w, h = lamp.box
        lit = bool(lamp_states and lamp_states.get(lamp.name))
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 255) if lit else (128, 128, 128), 2)
        cv2.putText(out, lamp.name + (" ON" if lit else ""), (x, y - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
    return out
