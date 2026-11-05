"""Stage A - classical needle reader (no training). Port-exact: mirrored in StageA.kt.

1. geometry: if rim points were tapped, the dial ellipse is mapped to a circle by an
   affine M. Instead of warping the image we cast rays in the corrected (circular)
   frame and map each sample point back through M^-1 into the original image.
2. "needle-ness" map on a crop around the dial:
      dark needle: n = clip((local_mean - gray) / max(local_mean, 16), 0, 1)
      (dark *relative to its neighbourhood*, so glare and shadows mostly cancel)
      red needle : n = red-hue mask * S/255 * min(V/120, 1)
3. sample n on 720 rays (0.5 deg) x 48 rings inside a radial band that holds the
   needle but not the tick marks or the needle tail/counterweight
4. per ring, subtract that ring's median (removes printed arcs / uneven light)
5. per ray, median over the band -> a ray must be dark along most of its length
6. circular Gaussian smoothing -> peak = needle angle (parabolic sub-bin refinement)
7. confidence from how much the peak stands out and how unique it is
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from .calibration import Calibration, apply_affine
from .geometry import Scale, dial_angle
from .imgops import to_gray, box_blur, bilinear, hsv, grid_sample

N_RAYS = 720          # 0.5 degree resolution
N_RINGS = 48
SMOOTH_SIGMA_BINS = 2.0
PEAK_EXCLUDE_DEG = 12
MIN_LOCAL_MEAN = 16.0


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
    g = to_gray(grid_sample(img, 64))
    mean, std = float(g.mean()), float(g.std())
    if mean < 25:
        return False, "frame_too_dark"
    if mean > 245 and std < 8:
        return False, "frame_blown_out"
    if std < 6:
        return False, "frame_uniform_camera_blocked"
    return True, ""


def blur_kernel(radius: float) -> int:
    return max(5, int(round(0.2 * radius)) | 1)


def needle_map(crop: np.ndarray, color: str, k: int) -> np.ndarray:
    """float32 map in [0,1]; high = looks like needle."""
    if color == "red":
        H, S, V = hsv(crop)
        red = ((H <= 10) | (H >= 165)).astype(np.float32)
        return red * (S.astype(np.float32) / 255.0) * np.minimum(V.astype(np.float32) / 120.0, 1.0)
    gray = to_gray(crop)
    mean = box_blur(gray, k)
    return np.clip((mean - gray) / np.maximum(mean, MIN_LOCAL_MEAN), 0.0, 1.0).astype(np.float32)


def geometry(cal: Calibration):
    """(centre, scale, radius, Minv) in the corrected frame. Minv maps corrected -> image."""
    rect = cal.rectification()
    if rect is None:
        return cal.center, cal.scale(), cal.radius, None
    M, rim_radius = rect
    c = apply_affine(M, cal.center)
    z = apply_affine(M, cal.zero_point)
    m = apply_affine(M, cal.max_point)
    scale = Scale(dial_angle(c[0], c[1], *z), dial_angle(c[0], c[1], *m),
                  cal.min_value, cal.max_value, cal.direction)
    Minv = cv2.invertAffineTransform(M)
    return c, scale, rim_radius, Minv


def ray_points(c, radius, r_in, r_out, Minv):
    thetas = np.arange(N_RAYS, dtype=np.float64) * (360.0 / N_RAYS)
    radii = np.linspace(r_in * radius, r_out * radius, N_RINGS)
    t = np.radians(thetas)[:, None]
    xs = c[0] + radii[None, :] * np.sin(t)
    ys = c[1] - radii[None, :] * np.cos(t)
    if Minv is not None:
        xs, ys = (Minv[0, 0] * xs + Minv[0, 1] * ys + Minv[0, 2],
                  Minv[1, 0] * xs + Minv[1, 1] * ys + Minv[1, 2])
    return xs, ys


def polar_profile(img: np.ndarray, cal: Calibration):
    c, scale, radius, Minv = geometry(cal)
    xs, ys = ray_points(c, radius, cal.needle_r_inner, cal.needle_r_outer, Minv)
    k = blur_kernel(cal.radius)
    H, W = img.shape[:2]
    pad = k + 2
    x0 = max(0, int(math.floor(xs.min())) - pad)
    y0 = max(0, int(math.floor(ys.min())) - pad)
    x1 = min(W, int(math.ceil(xs.max())) + pad + 1)
    y1 = min(H, int(math.ceil(ys.max())) + pad + 1)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None, scale
    nmap = needle_map(img[y0:y1, x0:x1], cal.needle_color, k)
    polar = bilinear(nmap, xs - x0, ys - y0)                   # (N_RAYS, N_RINGS)
    polar = polar - np.median(polar, axis=0, keepdims=True)    # per-ring background
    return np.median(polar, axis=1).astype(np.float64), scale  # per-ray, robust to text


def circular_smooth(p: np.ndarray, sigma_bins: float = SMOOTH_SIGMA_BINS) -> np.ndarray:
    k = int(math.ceil(sigma_bins * 3))
    x = np.arange(-k, k + 1)
    ker = np.exp(-0.5 * (x / sigma_bins) ** 2)
    ker /= ker.sum()
    padded = np.concatenate([p[-k:], p, p[:k]])
    return np.convolve(padded, ker, mode="valid")


def find_peak(profile: np.ndarray) -> tuple[float, float]:
    """Return (angle_deg, confidence) of the needle in a polar profile."""
    sm = circular_smooth(profile)
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
    excl = PEAK_EXCLUDE_DEG * N_RAYS // 360
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
    prof, scale = polar_profile(img, cal)
    if prof is None:
        return NeedleResult(None, None, 0.0, False, reason="dial_outside_frame")
    angle, conf = find_peak(prof)
    value, in_range = scale.value(angle)
    if not in_range:
        conf *= 0.5                      # needle deep in the dead zone is suspicious
    return NeedleResult(round(value, 3), round(angle, 2), round(conf, 3), in_range,
                        reason="" if conf > 0 else "no_needle_peak")


def draw_debug(img: np.ndarray, cal: Calibration, res: NeedleResult,
               lamp_states: dict | None = None) -> np.ndarray:
    out = img.copy()
    c, _, radius, Minv = geometry(cal)

    def to_img(p):
        if Minv is None:
            return int(round(p[0])), int(round(p[1]))
        q = apply_affine(Minv, p)
        return int(round(q[0])), int(round(q[1]))

    for f, col in ((1.0, (255, 200, 0)), (cal.needle_r_inner, (200, 200, 200)), (cal.needle_r_outer, (200, 200, 200))):
        pts = [to_img((c[0] + radius * f * math.sin(math.radians(a)), c[1] - radius * f * math.cos(math.radians(a))))
               for a in range(0, 361, 5)]
        cv2.polylines(out, [np.array(pts, np.int32)], False, col, 1, cv2.LINE_AA)
    for p, col in ((cal.zero_point, (0, 200, 0)), (cal.max_point, (0, 0, 255))):
        cv2.circle(out, (int(p[0]), int(p[1])), 5, col, -1, cv2.LINE_AA)
    if res.angle is not None:
        t = math.radians(res.angle)
        tip = to_img((c[0] + radius * 0.95 * math.sin(t), c[1] - radius * 0.95 * math.cos(t)))
        cv2.line(out, to_img(c), tip, (255, 0, 255), 2, cv2.LINE_AA)
    txt = (f"{res.value:.2f} {cal.unit}  conf {res.confidence:.2f}" if res.value is not None
           else f"UNREADABLE ({res.reason})")
    s = max(0.6, img.shape[1] / 1000)
    cv2.putText(out, txt, (10, int(30 * s)), cv2.FONT_HERSHEY_SIMPLEX, 0.8 * s, (0, 0, 0), int(4 * s), cv2.LINE_AA)
    cv2.putText(out, txt, (10, int(30 * s)), cv2.FONT_HERSHEY_SIMPLEX, 0.8 * s, (0, 255, 255), int(2 * s), cv2.LINE_AA)
    for lamp in cal.lamps:
        x, y, w, h = lamp.box
        lit = bool(lamp_states and lamp_states.get(lamp.name))
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 255) if lit else (128, 128, 128), 2)
        cv2.putText(out, lamp.name + (" ON" if lit else ""), (x, y - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45 * s, (0, 255, 255), 1, cv2.LINE_AA)
    return out
