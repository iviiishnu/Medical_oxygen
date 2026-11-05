"""Automatic reading: no calibration clicks.

    image -> find every round dial (Hough proposals refined by the keypoint model)
          -> read each dial (Stage A classical + Stage B model, fused) using the model's own
             centre / 0-mark / max-mark keypoints as the calibration
          -> find lit panel lamps anywhere in the image by colour (green / red / amber)
          -> verdict NORMAL / ABNORMAL / CAN'T TELL with a confidence %

The model finds WHERE the max mark is, not WHAT number is printed there (16 on the alarm box,
10 on the Magnate). That is solved by recognising the dial face: every known gauge has a reference
photo + calibration in samples/real/ (name.jpg + name.calibration.json); the dial in the new image
is matched against them (ORB features on the dial face) and the matching gauge's scale is used.
A dial that matches nothing is reported as an UNKNOWN gauge type (scale assumed, low confidence).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .calibration import Calibration
from .config import MonitorConfig
from .dataset import CROP_SCALE, IMGSZ, crop_affine, make_crop
from .pipeline import GaugePipeline

KPT_CENTER, KPT_TIP, KPT_ZERO, KPT_MAX = range(4)
DIAL_MIN_CONF = 0.5            # refined model detection confidence to accept a dial
BOX_TO_RADIUS = 2.2            # training labels: box = dial centre +- 1.1 R


# ---------------------------------------------------------------------------- dial finding
@dataclass
class Dial:
    center: tuple[float, float]
    radius: float
    det_conf: float
    kpts: np.ndarray                      # (4, 3) image px + keypoint conf


def _model_raw(model, img, cx, cy, r):
    """One model pass on the crop around (cx, cy, r) -> (det_conf, kpts(4,3) img px, box_wh img px)."""
    M = crop_affine(cx, cy, r, CROP_SCALE)
    crop = make_crop(img, M)
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    if model.backend == ".onnx":
        o = model.sess.run(None, {model.inp: np.transpose(rgb, (2, 0, 1))[None]})[0]
    elif model.backend == ".tflite":
        model.interp.set_tensor(model.in_det["index"], rgb[None])
        model.interp.invoke()
        o = model.interp.get_tensor(model.out_det["index"])
    else:
        raise ValueError("auto mode needs the .onnx or .tflite model")
    o = np.asarray(o, np.float32)[0]
    if o.shape[0] == 17:                                  # classic layout (5 + 3k, anchors)
        o = o.T
        i = int(np.argmax(o[:, 4]))
        row = o[i]
        conf, wh, k = float(row[4]), row[2:4], row[5:17].reshape(4, 3).astype(np.float64)
    else:                                                 # end-to-end rows x1 y1 x2 y2 conf cls kpts
        i = int(np.argmax(o[:, 4]))
        row = o[i]
        conf, wh, k = float(row[4]), np.array([row[2] - row[0], row[3] - row[1]]), row[6:18].reshape(4, 3).astype(np.float64)
    if k[:, :2].max() <= 1.5:                             # normalised coords (TFLite export)
        k[:, :2] *= IMGSZ
        wh = wh * IMGSZ
    Minv = cv2.invertAffineTransform(M)
    k[:, :2] = k[:, :2] @ Minv[:, :2].T + Minv[:, 2]
    return conf, k, np.asarray(wh, np.float64) / M[0, 0]


def _refine(model, img, cx, cy, r, steps=5):
    """Re-centre and re-size the crop on the model's own prediction until it stops moving.
    Returns the dial with det_conf zeroed if it never settles (bezels, round lamps, labels)."""
    for _ in range(steps):
        conf, k, wh = _model_raw(model, img, cx, cy, r)
        rn = float(np.clip(np.mean(wh) / BOX_TO_RADIUS, r / 1.6, r * 1.6))
        nx, ny = k[KPT_CENTER, :2]
        moved = math.dist((nx, ny), (cx, cy)) / r
        cx, cy, r = float(nx), float(ny), rn
        if moved < 0.01:
            break
    conf, k, wh = _model_raw(model, img, cx, cy, r)
    shift = math.dist(k[KPT_CENTER, :2], (cx, cy)) / r
    size = np.mean(wh) / BOX_TO_RADIUS / r
    if shift > 0.06 or not 0.85 <= size <= 1.15:          # not self-consistent -> not a dial
        conf = 0.0
    return Dial((float(cx), float(cy)), float(r), conf, k)


def _proposals(img) -> list[tuple[float, float, float]]:
    H, W = img.shape[:2]
    s = 800 / max(H, W)
    sm = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img
    s = min(s, 1.0)
    g = cv2.medianBlur(cv2.cvtColor(sm, cv2.COLOR_BGR2GRAY), 5)
    mn = min(sm.shape[:2])
    out = []
    for p2 in (40, 28):
        cs = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT, dp=1.2, minDist=mn * 0.08, param1=120, param2=p2,
                              minRadius=int(mn * 0.04), maxRadius=int(mn * 0.45))
        if cs is not None:
            out += [(x / s, y / s, r / s) for x, y, r in cs[0][:30]]
        if len(out) >= 8:
            break
    # coarse grid fallback so a dial Hough misses can still be reached
    mnf = min(H, W)
    for rf in (0.30, 0.16):
        r = rf * mnf
        step = 1.3 * r
        for y in np.arange(r, H - r * 0.5 + 1, step):
            for x in np.arange(r, W - r * 0.5 + 1, step):
                out.append((float(x), float(y), r))
    return out


def find_dials(img, model, max_dials: int = 4) -> list[Dial]:
    """All dials in the image, best first (biggest confident dial = the main gauge)."""
    first = []
    for cx, cy, r in _proposals(img):
        conf, k, wh = _model_raw(model, img, cx, cy, r)
        nx, ny = k[KPT_CENTER, :2]
        if conf >= 0.02 or k[KPT_CENTER, 2] >= 0.5:
            rn = float(np.clip(np.mean(wh) / BOX_TO_RADIUS, r / 1.6, r * 1.6))
            first.append((conf, float(nx), float(ny), rn))
    first.sort(reverse=True)
    seeds = []
    for c, x, y, r in first:                               # dedupe seeds by predicted centre
        if all(math.dist((x, y), (sx, sy)) > 0.5 * min(r, sr) for _, sx, sy, sr in seeds):
            seeds.append((c, x, y, r))
        if len(seeds) >= 3 * max_dials:
            break
    dials: list[Dial] = []
    for _, x, y, r in seeds:
        d = _refine(model, img, x, y, r)
        if d.det_conf < DIAL_MIN_CONF:
            continue
        # same dial twice, or one "dial" containing another (bezel around the face): keep the better
        clash = [e for e in dials if math.dist(d.center, e.center) < max(d.radius, e.radius)]
        if clash:
            e = clash[0]
            if d.det_conf > e.det_conf + 0.05:
                dials[dials.index(e)] = d
            continue
        dials.append(d)
    # main gauge = the biggest confident dial (confidence first, size breaks ties)
    dials.sort(key=lambda d: (round(d.det_conf, 1), d.radius), reverse=True)
    return dials[:max_dials]


# ---------------------------------------------------------------------------- which gauge is it?
@dataclass
class GaugeType:
    name: str
    min_value: float
    max_value: float
    unit: str
    r_in: float
    r_out: float
    needle_color: str


class GaugeLibrary:
    """Known gauges = reference photos with a calibration (samples/real/*.calibration.json).

    Two independent signatures of the dial face, so one bad photo condition does not break it:
      * ORB feature matches on the face (precise on sharp images, weak when blurred);
      * correlation of the unrolled scale ring (numbers + ticks), needle masked out, best over
        +-24 deg camera roll (survives blur, low resolution, dark and bright frames).
    A gauge is recognised when either signature is clearly confident and they do not contradict.
    """
    MIN_MATCHES = 12          # ORB: fewer good matches than this -> not confident
    MIN_RATIO = 3.0           # ORB: best type must beat the runner-up by this factor
    RING_MIN = 0.55           # ring correlation of the best type
    RING_GAP = 0.25           # ... and its lead over the runner-up
    NA, NR = 180, 24          # unrolled ring: angle bins x radius bins

    def __init__(self, folder: str | Path):
        import json
        self.orb = cv2.ORB_create(800)
        self.clahe = cv2.createCLAHE(2.0, (8, 8))
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.refs: list[tuple[GaugeType, np.ndarray, tuple]] = []
        for cj in sorted(Path(folder).glob("*.calibration.json")):
            img_path = cj.with_name(cj.name.replace(".calibration.json", ".jpg"))
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            cal = Calibration.load(cj)
            des = self._describe(img, cal.center, cal.radius)
            if des is None:
                continue
            nj = cj.with_name(cj.name.replace(".calibration.json", ".needle.json"))
            tip = json.loads(nj.read_text())["tip"] if nj.exists() else None
            ring = self._ring(img, cal.center, cal.radius, tip)
            t = GaugeType(img_path.stem, cal.min_value, cal.max_value, cal.unit,
                          cal.needle_r_inner, cal.needle_r_outer, cal.needle_color)
            self.refs.append((t, des, ring))

    def _describe(self, img, c, r):
        M = crop_affine(c[0], c[1], r, 1.05, size=256)
        g = self.clahe.apply(cv2.cvtColor(make_crop(img, M, 256), cv2.COLOR_BGR2GRAY))
        mask = np.zeros_like(g)
        cv2.circle(mask, (128, 128), 120, 255, -1)
        return self.orb.detectAndCompute(g, mask)[1]

    def _ring(self, img, c, r, tip=None):
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        x0, y0 = int(max(0, c[0] - 1.1 * r)), int(max(0, c[1] - 1.1 * r))
        g = g[y0:int(c[1] + 1.1 * r) + 1, x0:int(c[0] + 1.1 * r) + 1]
        a = np.deg2rad(np.arange(self.NA) * 360 / self.NA)
        rr = np.linspace(0.35, 0.98, self.NR) * r
        xs = (c[0] - x0 + np.outer(rr, np.sin(a))).astype(np.float32)
        ys = (c[1] - y0 - np.outer(rr, np.cos(a))).astype(np.float32)
        b = cv2.remap(cv2.GaussianBlur(g, (0, 0), max(1.0, r / 60)), xs, ys, cv2.INTER_LINEAR,
                      borderMode=cv2.BORDER_REPLICATE)
        w = np.ones(self.NA, np.float32)
        if tip is not None:                                  # the needle moves: leave it out
            ta = math.degrees(math.atan2(tip[0] - c[0], -(tip[1] - c[1]))) % 360
            ang = np.arange(self.NA) * 360 / self.NA
            for t in (ta, ta + 180):
                w[np.abs((ang - t + 180) % 360 - 180) < 14] = 0
        return b, w

    @staticmethod
    def _ring_score(q, ref, max_shift=12):
        (qb, qw), (rb, rw) = q, ref
        best = -1.0
        for s in range(-max_shift, max_shift + 1):
            w = qw * np.roll(rw, s)
            if w.sum() < 50:
                continue
            a, b = qb[:, w > 0], np.roll(rb, s, axis=1)[:, w > 0]
            a = (a - a.mean()) / (a.std() + 1e-6)
            b = (b - b.mean()) / (b.std() + 1e-6)
            best = max(best, float((a * b).mean()))
        return best

    def identify(self, img, d: "Dial") -> tuple[GaugeType | None, int]:
        """-> (gauge type or None, ORB match count of the best type)."""
        if not self.refs:
            return None, 0
        des = self._describe(img, d.center, d.radius)
        ring = self._ring(img, d.center, d.radius, d.kpts[KPT_TIP, :2])
        orb, rng = [], []
        for t, ref, rring in self.refs:
            n = 0
            if des is not None:
                ms = self.bf.knnMatch(des, ref, k=2)
                n = sum(1 for p in ms if len(p) == 2 and p[0].distance < 0.75 * p[1].distance)
            orb.append((n, t.name, t))
            rng.append((self._ring_score(ring, rring), t.name, t))
        orb.sort(key=lambda s: s[0], reverse=True)
        rng.sort(key=lambda s: s[0], reverse=True)
        o_best, o_t = orb[0][0], orb[0][2]
        o_ok = o_best >= self.MIN_MATCHES and o_best >= self.MIN_RATIO * max(orb[1][0] if len(orb) > 1 else 0, 1)
        r_best, r_t = rng[0][0], rng[0][2]
        r_ok = r_best >= self.RING_MIN and r_best - (rng[1][0] if len(rng) > 1 else -1) >= self.RING_GAP
        if o_ok and r_ok and o_t.name != r_t.name:
            return None, o_best                              # the two signatures contradict
        if o_ok:
            return o_t, o_best
        if r_ok:
            return r_t, o_best
        return None, o_best


def calibration_from_dial(d: Dial, max_value: float, min_value: float = 0.0,
                          r_in: float = 0.55, r_out: float = 0.85, needle_color: str = "dark",
                          unit: str = "kg/cm2") -> Calibration | None:
    try:
        cal = Calibration(center=[d.center[0], d.center[1]], radius=d.radius,
                          zero_point=d.kpts[KPT_ZERO, :2].tolist(), max_point=d.kpts[KPT_MAX, :2].tolist(),
                          min_value=min_value, max_value=max_value, unit=unit, needle_color=needle_color,
                          needle_r_inner=r_in, needle_r_outer=r_out, gauge_id="auto")
        cal.validate()
        return cal
    except ValueError:
        return None


# ---------------------------------------------------------------------------- lamps
HUES = {"red": [(0, 10), (165, 179)], "amber": [(11, 30)], "green": [(36, 95)]}
COLOR_MEANING = {"green": "NORMAL", "red": "LOW / ALARM", "amber": "HIGH / WARNING"}


@dataclass
class LitLamp:
    color: str
    box: tuple[int, int, int, int]
    area: int
    strength: float          # 0..1 how clearly it is a lit lamp


def find_lit_lamps(img, dials: list[Dial] | None = None) -> list[LitLamp]:
    """Lit indicator lamps anywhere in the frame, by colour.

    A LIT lamp is a blob of strongly saturated colour that is bright (lit LEDs saturate the
    camera: S >= 170, V >= 180). Paint, printed text, gold frames and unlit lamps are darker or
    duller and fail this. Blobs inside a dial face are ignored (coloured dial print / logos).
    """
    f = min(1.0, 800 / max(img.shape[:2]))                # lamps are big blobs: 800 px is plenty
    if f < 1.0:
        small_img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        sd = [Dial((d.center[0] * f, d.center[1] * f), d.radius * f, d.det_conf, d.kpts) for d in dials] if dials else dials
        out = find_lit_lamps(small_img, sd)
        return [LitLamp(l.color, tuple(int(round(t / f)) for t in l.box), int(l.area / f / f), l.strength) for l in out]
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    bright = (s >= 150) & (v >= 170)
    min_area = max(60, int(2e-4 * H * W))
    lamps = []
    # a lit lamp's centre is blown out to white: count white pixels touching the colour as part
    # of the same lamp, so the coloured ring around one hot centre stays ONE lamp
    white = ((v >= 230) & (s <= 70)).astype(np.uint8)
    nw, wlab, wst, _ = cv2.connectedComponentsWithStats(white, 8)
    small = np.zeros(nw, bool)
    small[1:] = wst[1:, 4] <= 0.01 * H * W                 # a lamp's hot centre, not a white wall
    small_white = small[wlab]
    k = max(5, int(0.006 * max(H, W)) | 1)
    for color, ranges in HUES.items():
        m = np.zeros_like(bright)
        for lo, hi in ranges:
            m |= (h >= lo) & (h <= hi)
        colored = (m & bright).astype(np.uint8)
        if not colored.any():
            continue
        near = cv2.dilate(colored, np.ones((k, k), np.uint8)) > 0
        keep = np.zeros(nw, np.uint8)
        keep[np.unique(wlab[near & small_white])] = 1
        keep[0] = 0
        hot = keep[wlab]
        mask = cv2.morphologyEx(colored | hot, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, lab, st, cen = cv2.connectedComponentsWithStats(mask, 8)
        for i in range(1, n):
            x, y, w, hh, a = (int(t) for t in st[i])
            sel = (lab[y:y + hh, x:x + w] == i) & (colored[y:y + hh, x:x + w] > 0)
            a_col = int(sel.sum())
            if a_col < min_area:
                continue
            cx, cy = cen[i]
            # on or around a dial = coloured dial print or a painted bezel (yellow vacuum gauge),
            # never a status lamp (bezels reach ~2.1 R; on both panels lamps sit 3.2-5 R away)
            if dials and any(math.dist((cx, cy), d.center) < 2.5 * d.radius for d in dials):
                continue
            S_med = float(np.median(s[y:y + hh, x:x + w][sel]))
            V_med = float(np.median(v[y:y + hh, x:x + w][sel]))
            if S_med < 170 or V_med < 180:
                continue
            # a LIT lamp emits light: it is brighter than what is around it, or has a white-hot
            # centre. Printed ink / paint is always darker than the panel around it.
            g = max(4, int(0.5 * max(w, hh)))
            X0, Y0, X1, Y1 = max(0, x - g), max(0, y - g), min(W, x + w + g), min(H, y + hh + g)
            blob = lab[Y0:Y1, X0:X1] == i
            ring = ~cv2.dilate(blob.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
            ring_v = float(np.median(v[Y0:Y1, X0:X1][ring])) if ring.any() else 0.0
            hot_frac = float(hot[y:y + hh, x:x + w][lab[y:y + hh, x:x + w] == i].mean())
            if V_med < ring_v + 15 and hot_frac < 0.05:
                continue
            strength = float(np.clip((S_med - 150) / 80, 0, 1) * np.clip((V_med - 160) / 60, 0, 1))
            lamps.append(LitLamp(color, (x, y, w, hh), a_col, round(strength, 2)))
    lamps.sort(key=lambda l: l.area, reverse=True)
    return lamps


# ---------------------------------------------------------------------------- verdict
@dataclass
class GaugeReading:
    value: float | None
    confidence: float
    stage_a: float | None
    stage_b: float | None
    status: str                  # OK / LOW / CRITICAL / UNCERTAIN
    dial: Dial
    cal: Calibration | None
    notes: list[str] = field(default_factory=list)
    gauge_type: str | None = None        # recognised gauge (reference name) or None = unknown
    scale: str = ""                      # e.g. "0-16 kg/cm2 (recognised: alarm_box)"
    scale_known: bool = True


@dataclass
class Verdict:
    verdict: str                 # NORMAL / ABNORMAL / CAN'T TELL
    confidence: float            # 0..0.99 - a camera reading is never 100 % certain
    reasons: list[str]

    def __post_init__(self):
        self.confidence = round(float(min(max(self.confidence, 0.0), 0.99)), 3)


def decide(g: GaugeReading | None, lamps: list[LitLamp], cfg: MonitorConfig) -> Verdict:
    """Combine needle and lamp evidence. Safety first: any red/amber lamp or a low needle -> ABNORMAL."""
    reasons = []
    # ---- needle evidence
    g_state, g_strength = None, 0.0
    if g is not None and g.value is not None and g.status != "UNCERTAIN":
        g_state = "OK" if g.value >= cfg.low_threshold else "LOW"
        margin = abs(g.value - cfg.low_threshold)
        g_strength = g.confidence * float(np.clip(0.4 + margin / 1.0, 0.4, 1.0))   # near the limit = less sure
        reasons.append(f"needle reads {g.value:.2f} (limit {cfg.low_threshold}) -> "
                       f"{'above' if g_state == 'OK' else 'BELOW'} the low limit")
    elif g is not None and g.value is not None:
        reasons.append(f"needle reading {g.value:.2f} is uncertain ({'; '.join(g.notes) or 'low confidence'})")
    else:
        reasons.append("no gauge needle could be read")
    if g is not None and not g.scale_known:
        g_strength *= 0.6
        reasons.append(f"gauge type NOT recognised - scale assumed {g.scale}; pick the scale to be sure")
    # ---- lamp evidence
    bad = [l for l in lamps if l.color in ("red", "amber")]
    good = [l for l in lamps if l.color == "green"]
    l_state, l_strength = None, 0.0
    if bad:
        l_state, l_strength = "BAD", max(l.strength for l in bad)
        reasons.append("lit " + ", ".join(f"{l.color.upper()} lamp ({COLOR_MEANING[l.color]})" for l in bad[:3]))
    elif good:
        l_state, l_strength = "GOOD", max(l.strength for l in good)
        reasons.append(f"{len(good)} lit GREEN lamp(s) (NORMAL)")
    else:
        reasons.append("no lit lamp seen")
    l_strength *= 0.9                                       # a lamp alone is strong but not proof

    if g_state is None and l_state is None:
        return Verdict("CAN'T TELL", 0.0, reasons)
    needle_bad = g_state == "LOW"
    lamp_bad = l_state == "BAD"
    if g_state and l_state:
        agree = needle_bad == lamp_bad
        if agree:
            conf = 1 - (1 - g_strength) * (1 - l_strength)
            return Verdict("ABNORMAL" if needle_bad else "NORMAL", conf, reasons)
        reasons.append("needle and lamp DISAGREE - check the panel")
        return Verdict("ABNORMAL", 0.5 * max(g_strength, l_strength), reasons)
    if g_state:
        return Verdict("ABNORMAL" if needle_bad else "NORMAL", g_strength, reasons)
    return Verdict("ABNORMAL" if lamp_bad else "NORMAL", l_strength, reasons)


# ---------------------------------------------------------------------------- one call
DEFAULT_LIBRARY = Path(__file__).resolve().parents[2] / "samples" / "real"
FALLBACK_MAX = 16.0


class AutoReader:
    def __init__(self, model, cfg: MonitorConfig | None = None, library: str | Path | None = DEFAULT_LIBRARY,
                 cache_types: bool = False):
        """cache_types: live video - remember a dial's recognised type while it stays in place."""
        self.model = model
        self.cfg = cfg or MonitorConfig.load()
        self.library = GaugeLibrary(library) if library else None
        self.cache_types = cache_types
        self._types: list[tuple[tuple[float, float], float, GaugeType | None, int, float]] = []

    def _identify(self, img, d: Dial):
        if not self.library:
            return None, 0
        if self.cache_types:
            import time
            now = time.time()
            self._types = [c for c in self._types if now - c[4] < 5.0]
            for c in self._types:
                if math.dist(c[0], d.center) < 0.25 * d.radius and abs(c[1] - d.radius) < 0.2 * d.radius and c[2]:
                    return c[2], c[3]
            t, n = self.library.identify(img, d)
            self._types.append((d.center, d.radius, t, n, now))
            return t, n
        return self.library.identify(img, d)

    def read_dial(self, img, d: Dial, max_value: float | None = None) -> GaugeReading:
        """max_value None = recognise the gauge and use its scale."""
        t, n = self._identify(img, d)
        if max_value is not None:
            lo, hi, unit = 0.0, float(max_value), "kg/cm2"
            r_in, r_out, col = (t.r_in, t.r_out, t.needle_color) if t else (0.55, 0.85, "dark")
            scale, known = f"0-{hi:g} {unit} (set by you)", True
        elif t is not None:
            lo, hi, unit, r_in, r_out, col = t.min_value, t.max_value, t.unit, t.r_in, t.r_out, t.needle_color
            scale, known = f"{lo:g}-{hi:g} {unit} (recognised: {t.name})", True
        else:
            lo, hi, unit, r_in, r_out, col = 0.0, FALLBACK_MAX, "kg/cm2", 0.55, 0.85, "dark"
            scale, known = f"0-{hi:g} {unit}", False
        cal = calibration_from_dial(d, hi, lo, r_in, r_out, col, unit)
        name = t.name if t else None
        if cal is None:
            return GaugeReading(None, 0.0, None, None, "UNCERTAIN", d, None, ["could not locate 0 / max marks"],
                                name, scale, known)
        msg, dbg = GaugePipeline(cal, self.cfg, self.model).read(img)
        a, b, f = dbg["stage_a"], dbg["stage_b"], dbg["fusion"]
        return GaugeReading(msg["value"], msg["confidence"], a.value, b.value if b else None,
                            msg["status"], d, cal, list(f.notes), name, scale, known)

    def read(self, img, max_value: float | None = None, dials: list[Dial] | None = None) -> dict:
        if dials is None:
            dials = find_dials(img, self.model)
        readings = [self.read_dial(img, d, max_value) for d in dials]
        # main gauge: a recognised one beats an unknown one; then the find_dials order (conf, size)
        readings.sort(key=lambda g: 0 if g.gauge_type else 1)
        lamps = find_lit_lamps(img, dials)
        main = readings[0] if readings else None
        v = decide(main, lamps, self.cfg)
        return {"verdict": v, "main": main, "readings": readings, "lamps": lamps}


# ---------------------------------------------------------------------------- drawing
LAMP_BGR = {"green": (0, 220, 0), "red": (0, 0, 255), "amber": (0, 190, 255)}
VERDICT_BGR = {"NORMAL": (60, 150, 30), "ABNORMAL": (30, 30, 210), "CAN'T TELL": (90, 90, 90)}


def draw(img, result: dict, show_header: bool = True):
    out = img.copy()
    sc = max(0.6, img.shape[1] / 1400)

    def txt(s, org, col, k=1.0, th=2):
        cv2.putText(out, s, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6 * sc * k, (0, 0, 0), int(th * sc) + 3, cv2.LINE_AA)
        cv2.putText(out, s, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6 * sc * k, col, int(th * sc), cv2.LINE_AA)

    for i, g in enumerate(result["readings"]):
        d = g.dial
        c = tuple(int(t) for t in d.center)
        col = (0, 255, 255) if i == 0 else (200, 200, 200)
        cv2.circle(out, c, int(d.radius), col, max(2, int(2 * sc)), cv2.LINE_AA)
        tip = tuple(int(t) for t in d.kpts[KPT_TIP, :2])
        cv2.line(out, c, tip, (255, 0, 255), max(2, int(3 * sc)), cv2.LINE_AA)
        for k, kc in ((KPT_ZERO, (0, 200, 0)), (KPT_MAX, (0, 0, 255))):
            cv2.circle(out, tuple(int(t) for t in d.kpts[k, :2]), max(4, int(5 * sc)), kc, -1, cv2.LINE_AA)
        label = f"{g.value:.2f}" if g.value is not None else "--"
        if i == 0:
            label = f"MAIN {label}  ({g.gauge_type or 'unknown type'})"
        txt(label, (c[0] - int(d.radius), c[1] - int(d.radius) - 8), col, 1.2 if i == 0 else 1.0)
    for l in result["lamps"]:
        x, y, w, h = l.box
        cv2.rectangle(out, (x, y), (x + w, y + h), LAMP_BGR[l.color], max(2, int(3 * sc)))
        txt(l.color.upper(), (x, max(14, y - 6)), LAMP_BGR[l.color], 0.9)
    if show_header:
        v = result["verdict"]
        hh = int(46 * sc)
        cv2.rectangle(out, (0, 0), (out.shape[1], hh), VERDICT_BGR[v.verdict], -1)
        txt(f"{v.verdict}   confidence {v.confidence * 100:.0f}%", (12, int(32 * sc)), (255, 255, 255), 1.3)
    return out
