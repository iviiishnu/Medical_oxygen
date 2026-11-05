"""Synthetic gauge-panel renderer.

Two uses:
  1. stand-in for the real panel photos while we wait for them (demo + tests)
  2. training data for the keypoint model (perfect labels, any value)

Adding a gauge type = adding one GaugeSpec to GAUGES. The photo-based
generator (photo_synth.py) produces the same ground-truth dict, so everything
downstream (labels, evaluation) is shared.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from .geometry import Scale, point_at

SS = 2  # supersampling factor for anti-aliased drawing


@dataclass(frozen=True)
class GaugeSpec:
    name: str
    min_value: float
    max_value: float
    major_step: float
    minor_step: float
    label_step: float
    zero_angle: float = 225.0         # dial angle of 0 (7:30 position)
    sweep: float = 270.0
    unit_text: str = "kg/cm2"
    title: str = "OXYGEN"
    outer_scale: tuple | None = None  # (max, label_step, unit) for a second (psi) scale
    lamps: tuple = ("NORMAL", "LOW")
    lamp_hues: tuple = ("green", "red")
    low_band: float | None = None     # red arc from min to this value
    needle_color: tuple = (25, 25, 25)

    @property
    def scale(self) -> Scale:
        return Scale(self.zero_angle, (self.zero_angle + self.sweep) % 360.0,
                     self.min_value, self.max_value, "cw")


GAUGES = {
    # single-dial "Alarming System" box, 0-16 kg/cm2, LOW / NORMAL lamps
    "alarm_box_16": GaugeSpec("alarm_box_16", 0, 16, 2, 0.5, 2, low_band=3.5),
    # Magnate panel oxygen gauge: inner 0-10 kg/cm2 + outer psi, HIGH/NORMAL/LOW lamps
    "magnate_10": GaugeSpec("magnate_10", 0, 10, 1, 0.2, 1, outer_scale=(140, 20, "psi"),
                            lamps=("HIGH", "NORMAL", "LOW"), lamp_hues=("amber", "green", "red"),
                            low_band=3.5, needle_color=(30, 30, 160)),
}

HUE_BGR = {"green": ((40, 200, 40), (25, 60, 25)),     # (lit, off)
           "red": ((40, 40, 235), (30, 30, 70)),
           "amber": ((20, 170, 255), (25, 60, 80))}


@dataclass
class Layout:
    width: int = 640
    height: int = 480
    cx: float = 250
    cy: float = 240
    radius: float = 170
    lamp_x: int = 470
    lamp_y0: int = 150
    lamp_size: int = 46
    lamp_gap: int = 80


def _pt(x, y):
    return int(round(x * SS)), int(round(y * SS))


def render_dial(spec: GaugeSpec, lay: Layout, rng: np.random.Generator | None = None) -> np.ndarray:
    """Panel + dial face WITHOUT needle and WITHOUT lamps, supersampled canvas."""
    rng = rng or np.random.default_rng(0)
    W, H = lay.width * SS, lay.height * SS
    base = np.array([150, 158, 165], np.float32) + rng.normal(0, 8, 3)
    img = np.empty((H, W, 3), np.float32)
    img[:] = base
    grad = np.linspace(-15, 15, H, dtype=np.float32)[:, None, None]
    img = np.clip(img + grad, 0, 255).astype(np.uint8)
    cx, cy, R = lay.cx, lay.cy, lay.radius

    cv2.circle(img, _pt(cx, cy), int((R * 1.12) * SS), (90, 90, 95), -1, cv2.LINE_AA)     # bezel
    cv2.circle(img, _pt(cx, cy), int((R * 1.08) * SS), (200, 200, 205), -1, cv2.LINE_AA)
    cv2.circle(img, _pt(cx, cy), int(R * 1.02 * SS), (245, 245, 242), -1, cv2.LINE_AA)    # face

    sc = spec.scale
    if spec.low_band is not None:                                    # red low-pressure arc
        a0, a1 = sc.angle(spec.min_value), sc.angle(spec.low_band)
        for a in np.linspace(a0, a0 + ((a1 - a0) % 360), 60):
            p = point_at(cx, cy, a, R * 0.83)
            cv2.circle(img, _pt(*p), int(R * 0.03 * SS), (60, 60, 210), -1, cv2.LINE_AA)
        a2 = sc.angle(spec.max_value * 0.75)
        for a in np.linspace(a1, a1 + ((a2 - a1) % 360), 80):
            p = point_at(cx, cy, a, R * 0.83)
            cv2.circle(img, _pt(*p), int(R * 0.03 * SS), (70, 170, 70), -1, cv2.LINE_AA)

    n_minor = int(round((spec.max_value - spec.min_value) / spec.minor_step))
    for i in range(n_minor + 1):
        v = spec.min_value + i * spec.minor_step
        a = sc.angle(v)
        major = abs((v / spec.major_step) - round(v / spec.major_step)) < 1e-6
        r0 = R * (0.86 if major else 0.91)
        p0, p1 = point_at(cx, cy, a, r0), point_at(cx, cy, a, R * 0.98)
        cv2.line(img, _pt(*p0), _pt(*p1), (20, 20, 20), int((3 if major else 1.4) * SS), cv2.LINE_AA)
        lab = abs((v / spec.label_step) - round(v / spec.label_step)) < 1e-6
        if lab:
            txt = f"{v:g}"
            fs = R / 170 * 0.75 * SS
            (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, fs, int(2 * SS))
            p = point_at(cx, cy, a, R * 0.73)
            cv2.putText(img, txt, (int(p[0] * SS - tw / 2), int(p[1] * SS + th / 2)),
                        cv2.FONT_HERSHEY_SIMPLEX, fs, (20, 20, 20), int(2 * SS), cv2.LINE_AA)

    if spec.outer_scale:                                             # psi labels near the rim
        omax, ostep, ounit = spec.outer_scale
        for v in np.arange(0, omax + 1e-6, ostep):
            a = (spec.zero_angle + v / omax * spec.sweep) % 360
            p = point_at(cx, cy, a, R * 0.94)
            txt = f"{v:g}"
            fs = R / 170 * 0.4 * SS
            (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, fs, SS)
            cv2.putText(img, txt, (int(p[0] * SS - tw / 2), int(p[1] * SS + th / 2)),
                        cv2.FONT_HERSHEY_SIMPLEX, fs, (40, 40, 140), SS, cv2.LINE_AA)

    for txt, dy, fs in ((spec.title, 0.42, 0.7), (spec.unit_text, 0.58, 0.5), ("USE NO OIL", 0.30, 0.4)):
        fsz = R / 170 * fs * SS
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, fsz, int(1.5 * SS))
        cv2.putText(img, txt, (int(cx * SS - tw / 2), int((cy + R * dy) * SS)),
                    cv2.FONT_HERSHEY_SIMPLEX, fsz, (30, 30, 30), int(1.5 * SS), cv2.LINE_AA)
    return img


def draw_needle(img_ss: np.ndarray, spec: GaugeSpec, lay: Layout, value: float) -> tuple:
    cx, cy, R = lay.cx, lay.cy, lay.radius
    a = spec.scale.angle(float(np.clip(value, spec.min_value, spec.max_value)))
    tip = point_at(cx, cy, a, R * 0.85)
    tail = point_at(cx, cy, (a + 180) % 360, R * 0.2)
    perp = math.radians(a + 90)
    def off(p, w):
        return (p[0] + w * math.sin(perp), p[1] - w * math.cos(perp))
    w_hub, w_tip = R * 0.035, R * 0.006
    poly = [off(tail, w_hub * 0.8), off((cx, cy), w_hub), off(tip, w_tip),
            off(tip, -w_tip), off((cx, cy), -w_hub), off(tail, -w_hub * 0.8)]
    pts = np.array([_pt(*p) for p in poly], np.int32)
    shadow = pts + np.array([int(3 * SS), int(4 * SS)])
    ov = img_ss.copy()
    cv2.fillPoly(ov, [shadow], (150, 150, 150), cv2.LINE_AA)
    cv2.addWeighted(ov, 0.35, img_ss, 0.65, 0, img_ss)
    cv2.fillPoly(img_ss, [pts], spec.needle_color, cv2.LINE_AA)
    cv2.circle(img_ss, _pt(cx, cy), int(R * 0.075 * SS), (40, 40, 40), -1, cv2.LINE_AA)
    cv2.circle(img_ss, _pt(cx, cy), int(R * 0.035 * SS), (60, 60, 200), -1, cv2.LINE_AA)
    return tip, a


def draw_lamps(img_ss: np.ndarray, spec: GaugeSpec, lay: Layout, lit: str | None) -> list:
    boxes = []
    s = lay.lamp_size
    for i, (name, hue) in enumerate(zip(spec.lamps, spec.lamp_hues)):
        x, y = lay.lamp_x, lay.lamp_y0 + i * lay.lamp_gap
        c = (x + s / 2, y + s / 2)
        on, off = HUE_BGR[hue]
        cv2.circle(img_ss, _pt(*c), int(s * 0.62 * SS), (60, 60, 60), -1, cv2.LINE_AA)
        cv2.circle(img_ss, _pt(*c), int(s * 0.5 * SS), on if lit == name else off, -1, cv2.LINE_AA)
        if lit == name:
            cv2.circle(img_ss, _pt(*c), int(s * 0.18 * SS), (235, 245, 250), -1, cv2.LINE_AA)
        fsz = 0.45 * SS
        cv2.putText(img_ss, name, _pt(x + s + 10, y + s / 2 + 5), cv2.FONT_HERSHEY_SIMPLEX,
                    fsz, (20, 20, 20), SS, cv2.LINE_AA)
        inset = int(s * 0.2)
        boxes.append({"name": name, "hue": hue, "box": [x + inset, y + inset, s - 2 * inset, s - 2 * inset]})
    return boxes


def lamp_for_value(spec: GaugeSpec, value: float, low_setpoint: float = 3.5,
                   high_setpoint: float | None = None) -> str:
    if value < low_setpoint:
        return "LOW"
    if high_setpoint is not None and value > high_setpoint and "HIGH" in spec.lamps:
        return "HIGH"
    return "NORMAL"


def render_scene(spec: GaugeSpec, value: float, lay: Layout | None = None, lit: str | None = "auto",
                 rng: np.random.Generator | None = None, dial_cache: np.ndarray | None = None):
    """Clean (un-augmented) frame + ground truth."""
    lay = lay or Layout()
    rng = rng or np.random.default_rng(0)
    canvas = (dial_cache.copy() if dial_cache is not None else render_dial(spec, lay, rng))
    if lit == "auto":
        lit = lamp_for_value(spec, value)
    boxes = draw_lamps(canvas, spec, lay, lit)
    tip, ang = draw_needle(canvas, spec, lay, value)
    img = cv2.resize(canvas, (lay.width, lay.height), interpolation=cv2.INTER_AREA)
    sc = spec.scale
    gt = {
        "gauge": spec.name, "value": float(value), "angle": ang,
        "center": [lay.cx, lay.cy], "radius": lay.radius, "tip": list(tip),
        "zero": list(point_at(lay.cx, lay.cy, sc.zero_angle, lay.radius * 0.95)),
        "max": list(point_at(lay.cx, lay.cy, sc.max_angle, lay.radius * 0.95)),
        "lamps": boxes, "lamp_state": lit or "OFF",
        "min_value": spec.min_value, "max_value": spec.max_value,
    }
    return img, gt


# --------------------------------------------------------------- augmentation
@dataclass
class AugParams:
    glare_p: float = 0.6
    blur_p: float = 0.4
    noise_p: float = 0.5
    jpeg_p: float = 0.6
    persp: float = 0.0          # max corner jitter as fraction of size (fixed camera: small)
    rot_deg: float = 0.0
    brightness: float = 0.25
    contrast: float = 0.25
    color_shift: float = 0.08
    extra: dict = field(default_factory=dict)


def add_glare(img: np.ndarray, rng, strength: float | None = None, center=None) -> np.ndarray:
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.float32)
    n = int(rng.integers(1, 3))
    for _ in range(n):
        c = center if center is not None else (int(rng.uniform(0.1, 0.9) * w), int(rng.uniform(0.1, 0.9) * h))
        ax = (int(rng.uniform(0.04, 0.15) * w), int(rng.uniform(0.02, 0.08) * h))
        cv2.ellipse(mask, c, ax, float(rng.uniform(0, 180)), 0, 360, 1.0, -1)
    k = int(max(w, h) * 0.04) | 1
    mask = cv2.GaussianBlur(mask, (k, k), 0)
    s = strength if strength is not None else rng.uniform(0.4, 0.95)
    out = img.astype(np.float32) + (255 - img.astype(np.float32)) * (mask[..., None] * s)
    return np.clip(out, 0, 255).astype(np.uint8)


def augment(img: np.ndarray, gt: dict, rng: np.random.Generator, p: AugParams) -> tuple[np.ndarray, dict]:
    gt = {**gt, "lamps": [dict(l) for l in gt["lamps"]]}
    h, w = img.shape[:2]
    if p.persp > 0 or p.rot_deg > 0:
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        dst = src + rng.uniform(-p.persp, p.persp, (4, 2)).astype(np.float32) * [w, h]
        if p.rot_deg > 0:
            R = cv2.getRotationMatrix2D((w / 2, h / 2), float(rng.uniform(-p.rot_deg, p.rot_deg)), 1.0)
            dst = (np.c_[dst, np.ones(4)] @ R.T).astype(np.float32)
        Hm = cv2.getPerspectiveTransform(src, dst)
        img = cv2.warpPerspective(img, Hm, (w, h), borderMode=cv2.BORDER_REPLICATE)
        def tf(pt):
            q = cv2.perspectiveTransform(np.float32([[pt]]), Hm)[0, 0]
            return [float(q[0]), float(q[1])]
        for k in ("center", "tip", "zero", "max"):
            gt[k] = tf(gt[k])
        for l in gt["lamps"]:
            x, y, bw, bh = l["box"]
            cs = np.array([tf((x, y)), tf((x + bw, y)), tf((x, y + bh)), tf((x + bw, y + bh))])
            x0, y0 = cs.min(0)
            x1, y1 = cs.max(0)
            l["box"] = [int(x0), int(y0), int(x1 - x0), int(y1 - y0)]
        gt["radius"] = gt["radius"] * float(np.sqrt(abs(np.linalg.det(Hm[:2, :2]))))
    f = img.astype(np.float32)
    f = f * (1 + rng.uniform(-p.contrast, p.contrast)) + rng.uniform(-p.brightness, p.brightness) * 128
    f = f * (1 + rng.uniform(-p.color_shift, p.color_shift, 3))
    img = np.clip(f, 0, 255).astype(np.uint8)
    if rng.random() < p.glare_p:
        img = add_glare(img, rng)
    if rng.random() < p.blur_p:
        if rng.random() < 0.5:
            k = int(rng.choice([3, 5]))
            img = cv2.GaussianBlur(img, (k, k), 0)
        else:
            k = int(rng.choice([3, 5, 7]))
            ker = np.zeros((k, k), np.float32)
            ker[k // 2, :] = 1.0 / k
            M = cv2.getRotationMatrix2D((k / 2 - 0.5, k / 2 - 0.5), float(rng.uniform(0, 180)), 1)
            ker = cv2.warpAffine(ker, M, (k, k))
            ker /= max(ker.sum(), 1e-6)
            img = cv2.filter2D(img, -1, ker)
    if rng.random() < p.noise_p:
        img = np.clip(img.astype(np.float32) + rng.normal(0, rng.uniform(2, 9), img.shape), 0, 255).astype(np.uint8)
    if rng.random() < p.jpeg_p:
        q = int(rng.integers(35, 90))
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return img, gt


def calibration_from_gt(gt: dict, device_id="tab-main-o2-01", gauge_id="oxygen_main") -> dict:
    """What a staff member would tap on this frame (perfect taps)."""
    return {
        "device_id": device_id, "gauge_id": gauge_id, "unit": "kg/cm2",
        "center": gt["center"], "radius": gt["radius"],
        "zero_point": gt["zero"], "max_point": gt["max"],
        "min_value": gt["min_value"], "max_value": gt["max_value"], "direction": "cw",
        "needle_color": "dark", "needle_r_inner": 0.30, "needle_r_outer": 0.62,
        "lamps": [{"name": l["name"], "box": l["box"], "hue": l["hue"]} for l in gt["lamps"]],
    }
