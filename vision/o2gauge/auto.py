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
from dataclasses import dataclass, field, replace
from pathlib import Path

import cv2
import numpy as np

from .calibration import Calibration
from .config import MonitorConfig
from .dataset import CROP_SCALE, IMGSZ, crop_affine, make_crop
from .dialtext import UNITS, VACUUM_UNITS
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
    direction: str = "cw"                 # ccw = numbers grow anticlockwise (vacuum 0..760)
    gas: str | None = None                # from the calibration's gauge_id: oxygen_* / air_* / vacuum_*


GAS_FROM_ID = {"oxygen": "OXYGEN", "o2": "OXYGEN", "air": "MEDICAL AIR", "vacuum": "VACUUM", "vac": "VACUUM",
               "n2o": "NITROUS OXIDE", "nitrous": "NITROUS OXIDE", "co2": "CARBON DIOXIDE", "nitrogen": "NITROGEN"}


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
        self.bezel: dict[str, np.ndarray] = {}
        self.ref_photo: dict[str, tuple[str, float]] = {}    # name -> (photo hash, dial x in that photo)
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
                          cal.needle_r_inner, cal.needle_r_outer, cal.needle_color, cal.direction,
                          GAS_FROM_ID.get(cal.gauge_id.split("_")[0].lower()))
            self.refs.append((t, des, ring))
            self.bezel[t.name] = self._bezel(img, cal.center, cal.radius)
            import hashlib
            self.ref_photo[t.name] = (hashlib.md5(img_path.read_bytes()).hexdigest(), float(cal.center[0]))

    @staticmethod
    def _scale_key(t):
        return (t.min_value, t.max_value, t.unit, t.direction)

    @staticmethod
    def _bezel(img, c, r):
        """Mean Lab colour of the ring around the dial (white oxygen / black-green air / yellow vacuum
        rings on the Magnate panel: the dial faces themselves are identical)."""
        x0, y0 = int(max(0, c[0] - 1.5 * r)), int(max(0, c[1] - 1.5 * r))
        crop = img[y0:int(c[1] + 1.5 * r) + 1, x0:int(c[0] + 1.5 * r) + 1]
        yy, xx = np.mgrid[:crop.shape[0], :crop.shape[1]]
        d = np.hypot(xx - (c[0] - x0), yy - (c[1] - y0)) / r
        m = (d > 1.2) & (d < 1.42)
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).reshape(-1, 3)[m.ravel()].astype(np.float32)
        # mean, not median: a two-colour bezel (black / white sectors of the Medical Air ring) has a
        # median that flips between the two colours with the camera angle; the mean stays put
        return np.mean(lab, 0) if len(lab) else np.zeros(3, np.float32)

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
        key = self._scale_key
        # the runner-up that matters is a gauge with a DIFFERENT scale: identical dial faces (oxygen and
        # air on the Magnate panel) match each other equally well, and are told apart by the bezel below
        o_best, o_t = orb[0][0], orb[0][2]
        o_2nd = next((s[0] for s in orb[1:] if key(s[2]) != key(o_t)), 0)
        o_ok = o_best >= self.MIN_MATCHES and o_best >= self.MIN_RATIO * max(o_2nd, 1)
        r_best, r_t = rng[0][0], rng[0][2]
        r_2nd = next((s[0] for s in rng[1:] if key(s[2]) != key(r_t)), -1)
        r_ok = r_best >= self.RING_MIN and r_best - r_2nd >= self.RING_GAP
        if o_ok and r_ok and key(o_t) != key(r_t):
            return None, o_best                              # the two signatures contradict
        t = o_t if o_ok else r_t if r_ok else None
        if t is None:
            return None, o_best
        same = [s[2] for s in orb if key(s[2]) == key(t)]
        if len(same) > 1:                                    # same face: pick by bezel colour
            q = self._bezel(img, d.center, d.radius)
            t = min(same, key=lambda s: float(np.linalg.norm(self.bezel[s.name] - q)))
        return t, o_best


# ---------------------------------------------------------------------------- camera angle
MIN_TILT_RATIO = 0.95          # rim axis ratio above this = seen (nearly) straight on: no correction

def rim_support(img, d: Dial) -> float:
    """Share of rays (0..1) that hit one clean elliptical edge near the dial rim. A real dial has a
    round rim / bezel; a 'dial' found between two dials or on a button does not."""
    try:
        return float(dial_rectifier(img, d, return_support=True))
    except (cv2.error, ValueError, np.linalg.LinAlgError):
        return 0.0


def dial_rectifier(img, d: Dial, min_inliers: float = 0.3, return_support: bool = False):
    """Seen at an angle a round dial is an ellipse, and equal steps of the scale stop being equal
    angles in the photo (readings come out a few % off). Fit the ellipse of the dial rim (RANSAC over
    the strongest radial edges) and return the 2x3 affine that turns it back into a circle around the
    dial centre, plus the axis ratio (1 = seen straight on). None when the rim is not clear enough."""
    cx, cy = d.center
    r = d.radius
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    g = cv2.GaussianBlur(g.astype(np.float32), (0, 0), max(1.0, r / 60))
    a = np.linspace(0, 2 * np.pi, 180, endpoint=False)
    rr = np.linspace(0.75 * r, 1.45 * r, 140)
    xs = (cx + np.outer(np.sin(a), rr)).astype(np.float32)
    ys = (cy - np.outer(np.cos(a), rr)).astype(np.float32)
    prof = cv2.remap(g, xs, ys, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    gr = np.abs(np.diff(prof, axis=1))
    rel = rr[:-1] / r
    rows = np.arange(len(a))
    rng = np.random.default_rng(0)

    def fit_band(lo, hi):
        """strongest edge per ray inside the band -> RANSAC ellipse -> (w, h, theta, inlier share)"""
        cols = np.where((rel >= lo) & (rel < hi))[0]
        if len(cols) < 3:
            return None
        j = cols[np.argmax(gr[:, cols], axis=1)]
        P = np.stack([xs[rows, j], ys[rows, j]], -1)
        strong = gr[rows, j] > 0.35 * np.median(gr[rows, j]) + 1.0
        P = P[strong]
        if len(P) < 40:
            return None

        def inl(e):
            (ex, ey), (w, h), th = e
            t = math.radians(th)
            R = np.array([[math.cos(t), math.sin(t)], [-math.sin(t), math.cos(t)]])
            q = (P - [ex, ey]) @ R.T
            return np.abs(np.hypot(q[:, 0] / (w / 2), q[:, 1] / (h / 2)) - 1) < 0.012

        best, best_n = None, 0
        for _ in range(250):
            try:
                e = cv2.fitEllipse(P[rng.choice(len(P), 6, replace=False)].astype(np.float32))
            except cv2.error:
                continue
            (ex, ey), (w, h), _ = e
            if not (1.3 * r < max(w, h) < 3.0 * r) or min(w, h) < 0.5 * max(w, h) \
                    or math.dist((ex, ey), (cx, cy)) > 0.15 * r:
                continue
            n = int(inl(e).sum())
            if n > best_n:
                best, best_n = e, n
        if best is None or best_n < 12:
            return None
        share = best_n / len(a)
        e = cv2.fitEllipse(P[inl(best)].astype(np.float32))
        return e[1][0], e[1][1], e[2], share

    # every concentric circle of the dial (face edge, bezel inside, bezel outside) is distorted the
    # same way: fit each band separately and keep the consensus (one band alone can lock onto text,
    # the needle or a two-colour bezel)
    fits = [f for f in (fit_band(0.8, 1.05), fit_band(1.0, 1.22), fit_band(1.18, 1.45)) if f]
    support = max((f[3] for f in fits), default=0.0)
    if return_support:
        return support
    fits = [f for f in fits if f[3] >= min_inliers + 0.1]
    if not fits:
        return None, 1.0
    ratios = np.array([min(w, h) / max(w, h) for w, h, _, _ in fits])
    if len(fits) >= 2:
        med = float(np.median(ratios))
        agree = [f for f, q in zip(fits, ratios) if abs(q - med) <= 0.03]
        if not agree:
            return None, 1.0
        fits = agree
    f = max(fits, key=lambda f: f[3])                                  # best-supported of the agreeing fits
    w, h, th, _ = f
    ratio = float(np.median([min(a_, b_) / max(a_, b_) for a_, b_, _, _ in fits]))
    # nearly straight on: the fit's own noise (+-0.03 in ratio) would cost more than the correction gains
    # (alarm box, ratio 0.965: corrected 4.94 vs 5.01 uncorrected, by eye 5.0-5.1)
    if ratio > MIN_TILT_RATIO:
        return None, ratio
    # rebuild with the consensus ratio along the best fit's minor axis
    if w < h:
        w, h = ratio * h, h
    else:
        w, h = w, ratio * w
    t = math.radians(th)
    R = np.array([[math.cos(t), math.sin(t)], [-math.sin(t), math.cos(t)]])
    A = R.T @ np.diag([max(w, h) / w, max(w, h) / h]) @ R
    c = np.array([cx, cy])
    return np.hstack([A, (c - A @ c)[:, None]]), ratio


def _warp_dial(d: Dial, M: np.ndarray) -> Dial:
    k = d.kpts.copy()
    k[:, :2] = k[:, :2] @ M[:, :2].T + M[:, 2]
    c = M[:, :2] @ np.asarray(d.center) + M[:, 2]
    return Dial((float(c[0]), float(c[1])), d.radius * math.sqrt(abs(np.linalg.det(M[:, :2]))), d.det_conf, k)


def calibration_from_dial(d: Dial, max_value: float, min_value: float = 0.0,
                          r_in: float = 0.55, r_out: float = 0.85, needle_color: str = "dark",
                          unit: str = "kg/cm2", direction: str = "cw") -> Calibration | None:
    try:
        cal = Calibration(center=[d.center[0], d.center[1]], radius=d.radius,
                          zero_point=d.kpts[KPT_ZERO, :2].tolist(), max_point=d.kpts[KPT_MAX, :2].tolist(),
                          min_value=min_value, max_value=max_value, direction=direction, unit=unit,
                          needle_color=needle_color,
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
            # an indicator lamp is a compact blob; painted pipes, cabinets and long strips are not
            if a_col > 0.03 * H * W or max(w, hh) > 4.5 * max(1, min(w, hh)) or a < 0.3 * w * hh:
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
    scale: str = ""                      # e.g. "0-16 kg/cm2 (read from the dial)"
    scale_known: bool = True
    gas: str | None = None               # OXYGEN / MEDICAL AIR / VACUUM ... read from the dial, or None
    unit: str = ""
    scale_source: str = ""               # dial text / reference photo / set by you / assumed
    secondary: str = ""                  # reading on a second printed scale, e.g. "55 psi (0-150 psi)"
    low_limit: float | None = None       # low limit in this gauge's own unit (oxygen-type gauges only)
    unit_per_kgcm2: float = 1.0
    number: int = 0                      # 1, 2, 3 ... left to right
    text: object = None                  # dialtext.DialText (debug)
    kind: str = "analog"                 # analog (needle dial) / digital (seven-segment display)
    box: tuple | None = None             # digital: digit-area box x0 y0 x1 y1

    @property
    def label(self):
        return f"#{self.number}" + (f" {self.gas}" if self.gas else "")


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
    lim = cfg.low_threshold if g is None or g.low_limit is None else g.low_limit
    per = 1.0 if g is None else g.unit_per_kgcm2
    if g is not None and g.value is not None and g.status != "UNCERTAIN":
        g_state = "OK" if g.value >= lim else "LOW"
        margin = abs(g.value - lim) / per                    # in kg/cm2
        g_strength = g.confidence * float(np.clip(0.4 + margin / 1.0, 0.4, 1.0))   # near the limit = less sure
        u = f" {g.unit}" if g.unit else ""
        reasons.append(f"{g.label} {'display' if g.kind == 'digital' else 'needle'} reads {g.value:.{_dp(g.value)}f}{u} (limit {lim:.{_dp(lim)}f}{u}) -> "
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
MAX_DIALS = 6
MIN_SCALE_CONF = 0.3          # a scale read from the printed numbers needs at least this confidence
MIN_RIM_SUPPORT_KNOWN = 0.25  # recognised gauge type (Magnate vacuum dial: 0.36-0.37; ghosts 0.21)
MIN_RIM_SUPPORT = 0.30       # (real dials 0.36-0.80, ghosts between dials / buttons 0.09-0.26) unrecognised dial: share of rays that must hit one clean elliptical rim


def dial_angle_pt(c, p):
    return math.degrees(math.atan2(p[0] - c[0], -(p[1] - c[1]))) % 360.0


def point_on(c, ang, r):
    t = math.radians(ang)
    return (c[0] + r * math.sin(t), c[1] - r * math.cos(t))


def _dp(v, step=None):
    """decimals to show: enough for the scale step / value size"""
    ref = abs(step) if step else abs(v)
    if ref >= 50:
        return 0
    if ref >= 5:
        return 1
    return 2


class AutoReader:
    def __init__(self, model, cfg: MonitorConfig | None = None, library: str | Path | None = DEFAULT_LIBRARY,
                 cache_types: bool = False, read_text: bool = False, debug: bool = False, rectify: bool = True,
                 digital: bool = True, panel_model=None):
        """panel_model: optional second keypoint model used to READ dials recognised as a known hospital
        gauge (the general model still finds every dial and reads unknown gauges)."""
        self.panel_model = panel_model
        """cache_types: live video - remember a dial's recognised type while it stays in place.
        read_text: read the printed numbers / words (needs vision/models/dialtext_*.onnx)."""
        self.model = model
        self.cfg = cfg or MonitorConfig.load()
        self.library = GaugeLibrary(library) if library else None
        self._debug = debug
        self.rectify = rectify
        self.text_always = False
        self.digital = None
        if digital:
            from .digital import DigitalReader
            if DigitalReader.available():
                self.digital = DigitalReader()
        self.text = None
        if read_text:
            from .dialtext import DialTextReader
            if DialTextReader.available():
                self.text = DialTextReader()
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

    def _read_text(self, img, d: Dial):
        if self.text is None:
            return None
        try:
            return self.text.read(img, d.center[0], d.center[1], d.radius, d.kpts)
        except Exception:                                        # never let text reading break a reading
            if self._debug:
                raise
            return None

    def read_dial(self, img, d: Dial, max_value: float | None = None) -> GaugeReading:
        """max_value None = read the scale off the dial (numbers printed on it); falls back to a
        reference-photo match, then to an assumed 0-16."""
        t, n = self._identify(img, d)
        reader_model = self.model
        if t is not None and self.panel_model is not None:
            # a recognised hospital gauge: read it with the model specialised on these panels
            dp = _refine(self.panel_model, img, d.center[0], d.center[1], d.radius, steps=2)
            if dp.det_conf >= DIAL_MIN_CONF:
                d, reader_model = dp, self.panel_model
        # printed numbers are read only for a gauge that matches no reference photo (they are slow, and a
        # recognised gauge already has an exact scale)
        dt = self._read_text(img, d) if max_value is None and (t is None or self.text_always) else None
        fit = dt.scales[0] if dt and dt.scales else None
        if fit is not None and fit.confidence < MIN_SCALE_CONF:
            fit = None
        r_in, r_out, col = (t.r_in, t.r_out, t.needle_color) if t else (0.55, 0.85, "dark")
        gas = (dt.gas if dt else None) or (t.gas if t else None)
        notes, secondary = [], ""
        direction = t.direction if t else "cw"
        zero_pt = max_pt = None
        if max_value is not None:
            lo, hi, unit = 0.0, float(max_value), "kg/cm2"
            source, known = "set by you", True
        elif fit is not None:
            lo, hi = fit.vmin, fit.vmax
            # the end marks are sometimes past the last printed number (vacuum 0..700 + 760 mark)
            # (only by one whole step: an end label hidden by the needle / stop pin)
            ext = sorted(fit.value_at(dial_angle_pt(d.center, d.kpts[k, :2])) for k in (KPT_ZERO, KPT_MAX))
            st = abs(fit.step)
            if abs(ext[0] - (lo - st)) < 0.3 * st:
                lo = lo - st
            if abs(ext[1] - (hi + st)) < 0.3 * st:
                hi = hi + st
            lo, hi = lo + 0.0, hi + 0.0                     # no "-0"
            unit = fit.unit or (t.unit if t else "")
            direction = "cw" if fit.b > 0 else "ccw"
            source, known = "read from the dial", True
            # (numbers inside the reference range also confirm it: the needle can hide an end number)
            same_dir = (fit.b > 0) == (t is None or t.direction == "cw")
            if t is not None and same_dir and t.min_value - 1e-6 <= lo and hi <= t.max_value + 1e-6:
                lo, hi = t.min_value, t.max_value
                # the numbers confirm a known gauge: its tick-mark geometry (model marks) is more precise
                # than the centres of the printed numbers, so keep that and use the numbers as a check
                source = f"read from the dial, matches reference '{t.name}'"
                unit = t.unit
            else:
                zero_pt = point_on(d.center, fit.angle_of(lo), 0.8 * d.radius)
                max_pt = point_on(d.center, fit.angle_of(hi), 0.8 * d.radius)
                if t is not None:
                    notes.append(f"looks like reference '{t.name}' ({t.min_value:g}-{t.max_value:g}) but the "
                                 f"dial reads {lo:g}-{hi:g}: using the dial")
        elif t is not None:
            lo, hi, unit = t.min_value, t.max_value, t.unit
            source, known = f"reference photo '{t.name}'", True
        else:
            lo, hi, unit = 0.0, FALLBACK_MAX, ""
            source, known = "assumed", False
        if fit is None and dt and dt.units and max_value is None:
            unit = unit or dt.units[0]
        name = t.name if t else None
        scale = f"{lo:g}-{hi:g}" + (f" {unit}" if unit else "") + f" ({source})"
        per = 98.0665 / UNITS[unit] if unit in UNITS else 1.0       # this unit per kg/cm2
        # vacuum: named so, a vacuum unit, all <= 0, or numbers that FALL clockwise (0..760 printed backwards)
        is_vac = gas == "VACUUM" or unit in VACUUM_UNITS or hi <= 0 or (fit is not None and fit.b < 0)
        low = None if is_vac or gas not in (None, "OXYGEN") else self.cfg.low_threshold * per
        # camera at an angle: read the needle on a view where the dial is a true circle again
        img_r, d_r = img, d
        try:
            M, _ = dial_rectifier(img, d) if self.rectify else (None, 1.0)
        except (cv2.error, ValueError, np.linalg.LinAlgError):
            if self._debug:
                raise
            M = None                                               # never let the angle fix break a reading
        if M is not None:
            img_r = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_REPLICATE)
            d_r = _warp_dial(d, M)
            if zero_pt is not None:
                zero_pt, max_pt = (tuple(M[:, :2] @ np.asarray(p) + M[:, 2]) for p in (zero_pt, max_pt))
        if zero_pt is not None:
            try:
                cal = Calibration(center=list(d_r.center), radius=d_r.radius, zero_point=list(zero_pt),
                                  max_point=list(max_pt), min_value=lo, max_value=hi, direction=direction,
                                  unit=unit or "kg/cm2", needle_color=col, needle_r_inner=r_in,
                                  needle_r_outer=r_out, gauge_id="auto")
                cal.validate()
            except ValueError:
                cal = None
        else:
            cal = calibration_from_dial(d_r, hi, lo, r_in, r_out, col, unit or "kg/cm2", direction)
        common = dict(gauge_type=name, scale=scale, scale_known=known, gas=gas, unit=unit, scale_source=source,
                      low_limit=low, unit_per_kgcm2=per, text=dt)
        if cal is None:
            return GaugeReading(None, 0.0, None, None, "UNCERTAIN", d, None, ["could not locate 0 / max marks"],
                                **common)
        # the fusion tolerances are in kg/cm2 on a 0-16 dial: scale them to this dial
        span = (hi - lo) / 16.0
        cfg = replace(self.cfg, agree_tolerance=self.cfg.agree_tolerance * span,
                      low_threshold=(low if low is not None else -1e9),
                      critical_threshold=(self.cfg.critical_threshold * per if low is not None else -2e9),
                      lamp_tolerance=self.cfg.lamp_tolerance * span)
        msg, dbg = GaugePipeline(cal, cfg, reader_model).read(img_r)
        a, b, f = dbg["stage_a"], dbg["stage_b"], dbg["fusion"]
        status = msg["status"]
        if low is None and status != "UNCERTAIN":
            status = "READ"                                       # no limit configured for this gas
        if not known and msg["value"] is not None and hi > lo:
            # scale numbers not readable: the needle's position on the dial is still exact
            secondary = f"{(msg['value'] - lo) / (hi - lo) * 100:.0f} % of the dial's full scale (numbers not readable)"
        if fit is not None and msg["value"] is not None and len(dt.scales) > 1:
            s2 = dt.scales[1]
            v2 = s2.value_at(fit.angle_of(msg["value"]))
            secondary = f"{v2:.{_dp(v2, s2.step)}f}" + (f" {s2.unit}" if s2.unit else "") + f" (scale {s2.describe()})"
        return GaugeReading(msg["value"], msg["confidence"], a.value, b.value if b else None,
                            status, d, cal, notes + list(f.notes), secondary=secondary, **common)

    def _unique_types(self, img, readings: list[GaugeReading]):
        """Identical dial faces (Magnate oxygen / air) are told apart by bezel colour, dial by dial. When two
        dials in one photo claim the SAME reference, assign the references jointly (each reference once,
        lowest total bezel-colour distance) - a panel never has two identical gauges of different gases
        labelled the same."""
        if not self.library:
            return
        import itertools
        by_type = {t.name: t for t, _, _ in self.library.refs}
        key = GaugeLibrary._scale_key
        groups: dict = {}
        for g in readings:
            if g.gauge_type in by_type:
                groups.setdefault(key(by_type[g.gauge_type]), []).append(g)
        for k, gs in groups.items():
            names = [t.name for t, _, _ in self.library.refs if key(t) == k]
            # (also when every dial already has its own type: oxygen and air can be swapped, not only duplicated)
            if len(gs) < 2 or len(names) < len(gs) or len(names) > 6:
                continue
            q = [self.library._bezel(img, g.dial.center, g.dial.radius) for g in gs]
            rp = self.library.ref_photo

            def cost(perm):
                c = sum(float(np.linalg.norm(self.library.bezel[n] - qi)) for n, qi in zip(perm, q))
                # references photographed together on one panel keep their left-to-right order
                for (g1, n1), (g2, n2) in itertools.combinations(zip(gs, perm), 2):
                    if rp[n1][0] == rp[n2][0] and (g1.dial.center[0] - g2.dial.center[0]) * (rp[n1][1] - rp[n2][1]) < 0:
                        c += 1000.0
                return c
            best = min(itertools.permutations(names, len(gs)), key=cost)
            for g, n in zip(gs, best):
                if g.gauge_type != n:
                    t = by_type[n]
                    g.gauge_type = n
                    g.gas = t.gas or g.gas
                    g.scale = g.scale.replace(f"'{g.scale.split(chr(39))[1]}'", f"'{n}'") if "'" in g.scale else g.scale
                    # only oxygen has a low limit: the gas decides whether this dial can alarm
                    if g.gas == "OXYGEN":
                        g.low_limit = self.cfg.low_threshold * g.unit_per_kgcm2
                        if g.value is not None and g.status != "UNCERTAIN":
                            g.status = "OK" if g.value >= g.low_limit else (
                                "CRITICAL" if g.value < self.cfg.critical_threshold * g.unit_per_kgcm2 else "LOW")
                    else:
                        g.low_limit = None
                        if g.status in ("OK", "LOW", "CRITICAL"):
                            g.status = "READ"

    def read_digital(self, img, analog: list[GaugeReading]) -> list[GaugeReading]:
        """Seven-segment displays -> readings (unit assumed kg/cm2 unless configured otherwise)."""
        if self.digital is None:
            return []
        try:
            found = self.digital.read(img)
        except Exception:
            if self._debug:
                raise
            return []
        out = []
        for r in found:
            x0, y0, x1, y1 = r.box
            c = ((x0 + x1) / 2, (y0 + y1) / 2)
            # a "display" inside an analog dial is printed text on the face, not a meter
            if any(math.dist(c, g.dial.center) < g.dial.radius for g in analog):
                continue
            if r.value is None and r.confidence < 0.5:
                continue
            # plausibility: a pressure display shows at most 5 digits; next to a needle gauge a printed
            # label can look like an LCD window, so then ask for a clearly confident detection
            ndig = sum(ch.isdigit() for ch in r.text)
            if ndig == 0 or ndig > 5:
                continue
            # (measured: printed "LOW" label at half size det 0.73 / read 0.77; a real meter det 0.80 / read 0.90)
            if analog and (r.det_conf < 0.77 or r.confidence < 0.85):
                continue
            d = Dial(c, max(4.0, (y1 - y0) / 2), r.det_conf, np.zeros((4, 3)))
            unit = self.cfg_digital_unit
            per = 98.0665 / UNITS[unit] if unit in UNITS else 1.0
            ok = r.value is not None and r.confidence >= 0.5
            status = ("OK" if r.value >= self.cfg.low_threshold * per else "LOW") if ok else "UNCERTAIN"
            notes = [] if ok else [f"display text '{r.text}' is not a clear number"]
            out.append(GaugeReading(r.value, r.confidence, None, None, status, d, None, notes,
                                    gauge_type="digital display", scale="digital display", scale_known=True,
                                    gas=None, unit=unit, scale_source="digits read off the display",
                                    low_limit=self.cfg.low_threshold * per, unit_per_kgcm2=per,
                                    kind="digital", box=r.box))
        return out

    cfg_digital_unit = "kg/cm2"

    def read(self, img, max_value: float | None = None, dials: list[Dial] | None = None) -> dict:
        if dials is None:
            dials = find_dials(img, self.model, MAX_DIALS)
            if self.panel_model is not None:
                # the panel specialist sometimes finds a hospital dial the general model misses (small / far)
                for d2 in find_dials(img, self.panel_model, MAX_DIALS):
                    if all(math.dist(d2.center, d.center) > 0.5 * min(d.radius, d2.radius) for d in dials):
                        dials.append(d2)
                dials = dials[:MAX_DIALS + 2]
        # a lit lamp is round and bright: never let it pass as an (unknown) dial - that would also hide
        # the lamp itself from the lamp check below (a red alarm lamp read as "dial #2")
        lit = find_lit_lamps(img, None)
        readings = [self.read_dial(img, d, max_value) for d in dials]
        readings = [g for g in readings if g.gauge_type or not any(
            math.dist(g.dial.center, (l.box[0] + l.box[2] / 2, l.box[1] + l.box[3] / 2)) < 0.6 * g.dial.radius
            for l in lit)]
        # a round "dial" that matches no known gauge and has no readable needle is something else
        # (a lit round lamp, a knob): drop it, otherwise the lamp next to it would be ignored too
        readings = [g for g in readings if g.gauge_type or g.status != "UNCERTAIN" or g.confidence >= 0.5]
        # an unrecognised "dial" with no clean round rim is a button, a lamp or a ghost between two dials
        # (a recognised gauge type lowers the bar - the yellow vacuum bezel gives a weak rim - but does not
        # remove it: a ghost circle can still match a reference face by chance)
        readings = [g for g in readings
                    if rim_support(img, g.dial) >= (MIN_RIM_SUPPORT_KNOWN if g.gauge_type else MIN_RIM_SUPPORT)]
        self._unique_types(img, readings)
        digital = self.read_digital(img, readings)
        readings += digital
        dials = [g.dial for g in readings if g.kind == "analog"]
        for i, g in enumerate(sorted(readings, key=lambda g: (g.dial.center[0], g.dial.center[1])), 1):
            g.number = i
        # main gauge = the oxygen gauge: named OXYGEN > unnamed pressure gauge > other gases;
        # then a known scale beats an assumed one; then find_dials order (conf, size)
        def rank(g):
            vac = (g.gas == "VACUUM" or g.unit in VACUUM_UNITS or (g.cal is not None and g.cal.max_value <= 0)
                   or (g.cal is not None and g.scale_source == "read from the dial" and g.cal.direction == "ccw"))
            gas = 0 if g.gas == "OXYGEN" else (1 if g.gas is None and not vac else 2)
            # a needle gauge outranks a digital display of the same tier (the dial is the proven reader)
            return (gas, 1 if g.kind == "digital" else 0, 0 if g.scale_known else 1)
        readings.sort(key=rank)
        lamps = find_lit_lamps(img, dials)
        # a lit LED display is not a status lamp
        for g in digital:
            x0, y0, x1, y1 = g.box
            m = 0.5 * (y1 - y0)
            lamps = [l for l in lamps if not (x0 - m <= l.box[0] + l.box[2] / 2 <= x1 + m
                                              and y0 - m <= l.box[1] + l.box[3] / 2 <= y1 + m)]
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
        if g.kind == "digital":
            x0, y0, x1, y1 = g.box
            cv2.rectangle(out, (x0, y0), (x1, y1), col, max(2, int(2 * sc)), cv2.LINE_AA)
            val = "--" if g.value is None else f"{g.value:g}"
            txt(f"{g.label} DIGITAL {val}" + (f" {g.unit}" if g.unit else ""), (x0, max(16, y0 - 8)), col,
                1.2 if i == 0 else 1.0)
            continue
        cv2.circle(out, c, int(d.radius), col, max(2, int(2 * sc)), cv2.LINE_AA)
        tip = tuple(int(t) for t in d.kpts[KPT_TIP, :2])
        cv2.line(out, c, tip, (255, 0, 255), max(2, int(3 * sc)), cv2.LINE_AA)
        for k, kc in ((KPT_ZERO, (0, 200, 0)), (KPT_MAX, (0, 0, 255))):
            cv2.circle(out, tuple(int(t) for t in d.kpts[k, :2]), max(4, int(5 * sc)), kc, -1, cv2.LINE_AA)
        val = f"{g.value:.{_dp(g.value, (g.cal.max_value - g.cal.min_value) / 10 if g.cal else None)}f}" \
            if g.value is not None else "--"
        label = f"{g.label} {val}" + (f" {g.unit}" if g.unit else "")
        txt(label, (c[0] - int(d.radius), c[1] - int(d.radius) - 8), col, 1.2 if i == 0 else 1.0)
        txt(f"scale {g.scale.split(' (')[0]}" + ("" if g.scale_known else " ?"),
            (c[0] - int(d.radius), c[1] + int(d.radius) + int(22 * sc)), col, 0.85)
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
