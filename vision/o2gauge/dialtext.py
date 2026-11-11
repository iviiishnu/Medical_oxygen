"""Read the printed text of a dial and turn it into the dial's scale.

    dial (centre, radius from the keypoint model)
      -> text detector on a dial crop + on the unrolled bezel ring
      -> text recogniser on every detected word / number (top-3 guesses per number)
      -> numbers + their angle around the centre -> the CHAIN of scale labels:
         neighbouring labels differ by one constant step (2, 25, 100, 0.2 ...) and sit at
         roughly even angles; a missing / hidden label is allowed, misreads (6 <-> 8, a tick
         read as a minus sign) are fixed by picking the guess that fits the chain
         (one chain per printed scale: e.g. kg/cm2 inside, psi outside)
      -> value <-> angle by interpolating between the labels (absorbs uneven printing and
         camera perspective)
      -> units (kg/cm2, bar, psi, kPa, MPa, mmHg, ...) and gas name (OXYGEN, AIR, VACUUM, ...)

Works for any range (0-1, 0-16, 0-250, 0-10000, vacuum 0-760 numbered anticlockwise, -1..0 bar)
because nothing is assumed about the numbers: they are read off the dial.
Models: vision/models/dialtext_det.onnx + dialtext_rec.onnx (train_dialtext.py, export_dialtext.py).
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .dialtext_geom import (CHARS, DET_SIZE, STRIP_H, STRIP_R0, STRIP_R1, dial_angle, dial_crop, dial_strips,
                            rec_crop, unclip)

MODELS = Path(__file__).resolve().parents[2] / "vision" / "models"
DIGITS = "0123456789.-"
NUM_IDX = np.array([0] + [CHARS.index(c) + 1 for c in DIGITS])
NUM_RE = re.compile(r"^-?(\d+(\.\d+)?|\.\d+)$")

# kPa per unit
UNITS = {"kg/cm2": 98.0665, "bar": 100.0, "psi": 6.89476, "kPa": 1.0, "MPa": 1000.0, "mmHg": 0.133322,
         "cmHg": 1.33322, "inHg": 3.38639, "mbar": 0.1}
UNIT_SPELL = {"KG/CM2": "kg/cm2", "KGF/CM2": "kg/cm2", "KG/CM": "kg/cm2", "KGCM2": "kg/cm2", "KGFCM2": "kg/cm2",
              "BAR": "bar", "PSI": "psi", "LB/IN2": "psi", "KPA": "kPa", "MPA": "MPa", "MMHG": "mmHg",
              "CMHG": "cmHg", "INHG": "inHg", "MBAR": "mbar"}
VACUUM_UNITS = {"mmHg", "cmHg", "inHg"}
GAS = {"OXYGEN": ["OXYGEN", "O2", "OXY"], "MEDICAL AIR": ["MEDICALAIR", "AIR", "SURGICALAIR"],
       "VACUUM": ["VACUUM", "VAC", "SUCTION"], "NITROUS OXIDE": ["NITROUSOXIDE", "N2O", "NITROUS"],
       "CARBON DIOXIDE": ["CARBONDIOXIDE", "CO2"], "NITROGEN": ["NITROGEN", "N2"], "AGSS": ["AGSS"],
       "HELIUM": ["HELIUM"], "ARGON": ["ARGON"]}


def _lev(a, b):
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        p, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (ca != cb))
    return d[-1]


def match_unit(text):
    t = re.sub(r"[\s.]", "", text.upper()).replace("²", "2")
    if t in UNIT_SPELL:
        return UNIT_SPELL[t]
    for k, u in UNIT_SPELL.items():
        if len(k) >= 5 and _lev(t, k) <= 1:
            return u
    return None


def match_gas(text, conf=1.0):
    """Gas name in a word. Short names (O2, N2, AIR ...) are easy to misread from other text, so
    they need a confident reading of a token that is exactly that name."""
    up = text.upper()
    joined = re.sub(r"[^A-Z0-9]", "", up)
    tokens = [t for t in re.split(r"[^A-Z0-9]+", up) if t]
    for name, keys in GAS.items():
        for k in keys:
            if len(k) <= 4:
                if (joined == k or k in tokens) and conf >= 0.8:
                    return name
                continue
            if joined == k or k in tokens:
                return name
            if len(k) >= 6 and (_lev(joined, k) <= (1 if len(k) < 9 else 2)):
                return name
    return None


def nice_step(d):
    """1.0 for printed-gauge steps (1, 2, 2.5, 5 x 10^k), less for unusual ones."""
    d = abs(d)
    if d <= 0:
        return 0.0
    m = d / 10 ** math.floor(math.log10(d) + 1e-9)
    for c, w in ((1, 1.0), (2, 1.0), (2.5, 1.0), (5, 1.0), (10, 1.0), (1.5, 0.8), (3, 0.8), (4, 0.8), (6, 0.6),
                 (7.5, 0.6)):
        if abs(m - c) < 1e-6 * c:
            return w
    return 0.4


# ---------------------------------------------------------------------------- data
@dataclass
class TextBox:
    text: str
    conf: float
    num: float | None          # best numeric reading (None = a word)
    num_conf: float
    x: float                   # centre in image px
    y: float
    h: float                   # text height in image px
    where: str                 # face / bezel_top / bezel_bottom
    angle: float = 0.0         # dial angle of the centre
    rho: float = 0.0           # distance from centre / dial radius
    alts: list = field(default_factory=list)   # [(value, weight)] numeric guesses, best first


@dataclass
class ScaleFit:
    gap: float                 # dial angle of the dead-zone centre; t = (angle - gap) % 360
    t: np.ndarray              # label positions (deg from the gap, increasing)
    v: np.ndarray              # label values in the same order
    labels: list               # TextBox per label (same order)
    step: float                # printed step between neighbouring labels (signed: < 0 = falls clockwise)
    score: float = 0.0
    unit: str = ""
    unit_inferred: bool = False
    resid: float = 0.0         # rms deviation from a straight line (deg)

    @property
    def vmin(self):
        return float(self.v.min())

    @property
    def vmax(self):
        return float(self.v.max())

    @property
    def b(self):
        """degrees per unit (global straight-line fit); > 0 = values grow clockwise"""
        return float(np.polyfit(self.v, self.t, 1)[0])

    @property
    def height(self):
        return float(np.median([l.h for l in self.labels]))

    @property
    def rho(self):
        return float(np.median([l.rho for l in self.labels]))

    def value_at(self, dial_ang):
        t = (dial_ang - self.gap) % 360.0
        if t < self.t[0]:
            return float(self.v[0] + (t - self.t[0]) / self._end_slope(0))
        if t > self.t[-1]:
            return float(self.v[-1] + (t - self.t[-1]) / self._end_slope(-1))
        return float(np.interp(t, self.t, self.v))

    def angle_of(self, val):
        v, t = (self.v, self.t) if self.v[-1] > self.v[0] else (self.v[::-1], self.t[::-1])
        if val < v[0] or val > v[-1]:
            end = 0 if (val < v[0]) == (self.v[-1] > self.v[0]) else -1
            tt = self.t[end] + (val - self.v[end]) * self._end_slope(end)
        else:
            tt = float(np.interp(val, v, t))
        return (self.gap + tt) % 360.0

    def _end_slope(self, end):
        """deg per unit of the end segment (for extrapolating past the last label)"""
        if end == 0:
            dt, dv = self.t[1] - self.t[0], self.v[1] - self.v[0]
        else:
            dt, dv = self.t[-1] - self.t[-2], self.v[-1] - self.v[-2]
        return dt / dv

    @property
    def confidence(self):
        n = len(self.labels)
        w = float(np.mean(getattr(self, "_weights", None) or [l.num_conf for l in self.labels]))
        per_step = abs(self.b * self.step)
        reg = self.resid / max(per_step, 1e-6)
        return float(np.clip((n - 2) / 4, 0, 1) * w * np.clip(1.25 - 2 * reg, 0, 1) * nice_step(self.step))

    def describe(self):
        u = f" {self.unit}" if self.unit else ""
        return f"{self.vmin:g}-{self.vmax:g}{u}"


@dataclass
class DialText:
    boxes: list = field(default_factory=list)
    scales: list = field(default_factory=list)       # ScaleFit, primary first
    units: list = field(default_factory=list)         # units seen on the face
    gas: str | None = None
    gas_text: str = ""


# ---------------------------------------------------------------------------- CTC decoding
def ctc_greedy(p, allowed=None):
    q = p if allowed is None else p[:, allowed]
    k = q.argmax(-1)
    if allowed is not None:
        k = allowed[k]
    s, confs, prev = [], [], 0
    for t, c in enumerate(k):
        if c != prev and c != 0:
            s.append(CHARS[c - 1])
            confs.append(p[t, c])
        prev = c
    return "".join(s), float(np.min(confs)) if confs else 0.0


def ctc_beam_numbers(p, beam=6, top=3):
    """Prefix beam search over digits / '.' / '-' -> [(string, share of probability)], valid numbers only."""
    beams = {"": (1.0, 0.0)}                    # prefix -> (p ending in blank, p ending in a char)
    cls = NUM_IDX[1:]
    for t in range(p.shape[0]):
        pt = p[t]
        live = [c for c in cls if pt[c] > 1e-3]
        nxt = defaultdict(lambda: [0.0, 0.0])
        for pre, (pb, pnb) in beams.items():
            nxt[pre][0] += (pb + pnb) * pt[0]
            for c in live:
                ch = CHARS[c - 1]
                pc = pt[c]
                if pre and pre[-1] == ch:
                    nxt[pre][1] += pnb * pc
                    nxt[pre + ch][1] += pb * pc
                else:
                    nxt[pre + ch][1] += (pb + pnb) * pc
        beams = dict(sorted(((k, tuple(v)) for k, v in nxt.items()), key=lambda kv: -(kv[1][0] + kv[1][1]))[:beam])
    tot = sum(a + b for a, b in beams.values()) or 1.0
    out = [(s, (a + b) / tot) for s, (a, b) in beams.items() if NUM_RE.match(s)]
    return sorted(out, key=lambda x: -x[1])[:top]


# ---------------------------------------------------------------------------- reader
class DialTextReader:
    def __init__(self, det_path=MODELS / "dialtext_det.onnx", rec_path=MODELS / "dialtext_rec.onnx", threads=0):
        import onnxruntime as ort
        so = ort.SessionOptions()
        if threads:
            so.intra_op_num_threads = threads
        self.det = ort.InferenceSession(str(det_path), so, providers=["CPUExecutionProvider"])
        self.rec = ort.InferenceSession(str(rec_path), so, providers=["CPUExecutionProvider"])

    @staticmethod
    def available(det_path=MODELS / "dialtext_det.onnx", rec_path=MODELS / "dialtext_rec.onnx"):
        return Path(det_path).exists() and Path(rec_path).exists()

    def detect(self, img):
        x = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)[None].transpose(0, 3, 1, 2) / 255.0
        p = 1 / (1 + np.exp(-self.det.run(None, {"image": x})[0][0, 0]))
        n, lab, st, _ = cv2.connectedComponentsWithStats((p > 0.5).astype(np.uint8), 4)
        boxes = []
        for i in range(1, n):
            x0, y0, w, h, a = st[i]
            if a < 3:
                continue
            b = unclip(2 * x0, 2 * y0, 2 * (x0 + w), 2 * (y0 + h))
            boxes.append((b, float(p[lab == i].mean())))
        return boxes, p

    def recognise(self, crops):
        """-> [(text, conf, numeric guesses [(value, weight)])]"""
        if not crops:
            return []
        lg = self.rec.run(None, {"text": np.stack(crops)[:, None].astype(np.float32)})[0]
        lg = lg - lg.max(-1, keepdims=True)
        pr = np.exp(lg)
        pr /= pr.sum(-1, keepdims=True)
        out = []
        for p in pr:
            txt, conf = ctc_greedy(p)
            ntxt, nconf = ctc_greedy(p, NUM_IDX)
            alts = []
            # a number if the free reading is numeric, or the digits-only reading is about as likely
            if NUM_RE.match(txt) or (NUM_RE.match(ntxt) and nconf >= 0.5 * conf and nconf > 0.3):
                for s, share in ctc_beam_numbers(p):
                    w = share * max(nconf, 0.05)
                    v = float(s)
                    alts.append((v, w))
                    if v < 0:                         # a tick mark read as a minus sign
                        alts.append((-v, 0.6 * w))
                    if s.startswith("0") and len(s) > 1 and "." not in s:
                        alts.append((float(s[1:]), 0.5 * w))     # a tick read as a leading 0
            out.append((txt, conf, alts))
        return out

    def read(self, img, cx, cy, r, kpts=None) -> DialText:
        out = DialText()
        crop, M = dial_crop(img, cx, cy, r)
        Minv = cv2.invertAffineTransform(M)
        k = M[0, 0]
        crops, meta = [], []
        for (x0, y0, x1, y1), sc in self.detect(crop)[0]:
            c = rec_crop(crop, (x0, y0, x1, y1))
            if c is None:
                continue
            ix, iy = Minv @ np.array([(x0 + x1) / 2, (y0 + y1) / 2, 1.0])
            crops.append(c)
            meta.append((float(ix), float(iy), (y1 - y0 - 0.24 * (y1 - y0)) / k, "face"))
        strips, (mx, my) = dial_strips(img, cx, cy, r)
        for (x0, y0, x1, y1), sc in self.detect(strips)[0]:
            c = rec_crop(strips, (x0, y0, x1, y1))
            if c is None or (x1 - x0) < 1.2 * (y1 - y0):
                continue
            yy = int(np.clip((y0 + y1) / 2, 0, 2 * STRIP_H - 1))
            xx = int(np.clip((x0 + x1) / 2, 0, DET_SIZE - 1))
            crops.append(c)
            meta.append((float(mx[yy, xx]), float(my[yy, xx]), (y1 - y0) * (STRIP_R1 - STRIP_R0) * r / STRIP_H,
                         "bezel_top" if yy < STRIP_H else "bezel_bottom"))
        for (txt, conf, alts), (ix, iy, h, where) in zip(self.recognise(crops), meta):
            num, nconf = (alts[0][0], alts[0][1]) if alts else (None, 0.0)
            out.boxes.append(TextBox(txt, conf, num, nconf, ix, iy, h, where, dial_angle(cx, cy, ix, iy),
                                     math.dist((ix, iy), (cx, cy)) / r, alts))
        for b in out.boxes:
            if b.num is None and b.where == "face":
                u = match_unit(b.text)
                if u and u not in out.units:
                    out.units.append(u)
        gas = [(b, match_gas(b.text, b.conf)) for b in out.boxes if b.num is None and b.conf > 0.5]
        gas = [(b, g) for b, g in gas if g and (b.where != "face" or b.rho < 1.0)]
        if gas:
            b, g = max(gas, key=lambda bg: (bg[0].where != "face", bg[0].conf * len(bg[0].text)))
            out.gas, out.gas_text = g, b.text
        out.scales = fit_scales([b for b in out.boxes if b.alts and b.where == "face"], kpts, cx, cy)
        assign_units(out.scales, out.units)
        return out


# ---------------------------------------------------------------------------- scale fitting
def _gap_candidates(labels, kpts, cx, cy):
    """Possible dial angles of the middle of the dead zone (the scale may not wrap across it).
    The widest gaps between numbers (a stray number such as 'CL 1.6' can split the real gap),
    the keypoint model's 0 / max marks, and straight down; the best chain wins."""
    c = []
    angs = sorted(l.angle for l in labels)
    if len(angs) >= 3:
        gaps = sorted((((angs[(i + 1) % len(angs)] - angs[i]) % 360, angs[i]) for i in range(len(angs))),
                      reverse=True)
        c += [(a0 + g / 2) % 360 for g, a0 in gaps[:2] if g >= 25]
    if kpts is not None:
        za = dial_angle(cx, cy, *kpts[2, :2])
        ma = dial_angle(cx, cy, *kpts[3, :2])
        g = (za - ma) % 360
        if 20 < g < 200:
            c.append((ma + g / 2) % 360)
    c.append(180.0)
    out = []
    for a in c:
        if all(abs((a - b + 180) % 360 - 180) > 8 for b in out):
            out.append(a)
    return out


def fit_scales(labels, kpts=None, cx=0.0, cy=0.0, max_scales=2, min_conf2=0.3):
    labels = [l for l in labels if 0.25 <= l.rho <= 1.4 and l.alts]
    gaps = _gap_candidates(labels, kpts, cx, cy)
    fits = []
    pool = list(labels)
    for k in range(max_scales):
        cands = [f for f in (_chain(pool, g) for g in gaps) if f is not None]
        if not cands:
            break
        f = max(cands, key=lambda f: f.score)
        if k > 0 and (f.confidence < min_conf2 or len(f.labels) < 4):
            break                                  # a second scale must be clearly there
        fits.append(f)
        for l, v, w in zip(f.labels, f.v, f._weights):    # the guess that fits the chain wins
            l.num, l.num_conf = float(v), float(w)
        used = {id(l) for l in f.labels}
        pool = [l for l in pool if id(l) not in used]
    # primary: the scale with the bigger numbers (unless it has far fewer labels)
    fits.sort(key=lambda f: (len(f.labels) < 4, -f.height))
    return fits


def _same(a, b):
    return abs(a - b) <= 1e-6 * max(1.0, abs(b))


def _chain(labels, gap, ang_tol=0.4):
    n = len(labels)
    if n < 3:
        return None
    t = [(l.angle - gap) % 360 for l in labels]
    best = None
    for i in range(n):
        for j in range(n):
            dt = t[j] - t[i]
            if i == j or not 8 <= dt <= 120 or t[i] < 2 or t[j] > 358:
                continue
            li, lj = labels[i], labels[j]
            if abs(li.rho - lj.rho) > 0.15 or not 0.6 < li.h / lj.h < 1.65:
                continue
            for vi, wi in li.alts:
                for vj, wj in lj.alts:
                    d = round(vj - vi, 9)
                    if d == 0 or nice_step(d) < 0.5:
                        continue
                    chain = _walk(labels, t, i, j, vi, vj, dt, d, ang_tol)
                    if len(chain) < 3:
                        continue
                    span = chain[-1][1] - chain[0][1]
                    if span < 45 or span > 345:
                        continue
                    score = (sum(w for _, _, _, w in chain) + 0.3 * len(chain)) * nice_step(d)
                    if best is None or score > best[0]:
                        best = (score, chain, d)
    if best is None:
        return None
    score, chain, d = best
    tt = np.array([c[1] for c in chain])
    vv = np.array([c[2] for c in chain])
    labs = [labels[idx] for idx, _, _, _ in chain]
    b, a = np.polyfit(vv, tt, 1)
    resid = float(np.sqrt(np.mean((a + b * vv - tt) ** 2)))
    f = ScaleFit(gap, tt, vv, labs, d, score, resid=resid)
    f._weights = [w for _, _, _, w in chain]
    return f


def _walk(labels, t, i, j, vi, vj, dt, d, tol):
    """Grow the chain i -> j both ways: next label = value +- m*d at about +- m*dt degrees
    (m = 1, or 2 / 3 when labels are hidden). Returns [(label index, t, value, weight)] sorted by t."""
    ref = labels[i]
    used = {i, j}
    w_of = lambda k, v: next((w for a, w in labels[k].alts if _same(a, v)), 0.0)
    chain = [(i, t[i], vi, w_of(i, vi)), (j, t[j], vj, w_of(j, vj))]
    for direction in (1, -1):
        cur_t, cur_v = (t[j], vj) if direction == 1 else (t[i], vi)
        step_t = dt
        while True:
            found = None
            for m in (1, 2, 3):                    # up to two labels in a row hidden / unread
                target = cur_v + direction * m * d
                lo, hi = m * step_t * (1 - tol), m * step_t * (1 + tol)
                cands = []
                for k, l in enumerate(labels):
                    if k in used or abs(l.rho - ref.rho) > 0.15 or not 0.6 < l.h / ref.h < 1.65:
                        continue
                    gap_t = (t[k] - cur_t) * direction
                    if not lo <= gap_t <= hi or not 2 <= t[k] <= 358:
                        continue
                    w = w_of(k, target)
                    if w > 0:
                        cands.append((w, k))
                if cands:
                    w, k = max(cands)
                    exact = next(a for a, _ in labels[k].alts if _same(a, target))   # the label's own value
                    found = (k, m, w, exact)
                    break
            if found is None:
                break
            k, m, w, target = found
            used.add(k)
            step_t = 0.5 * step_t + 0.5 * abs(t[k] - cur_t) / m
            cur_t, cur_v = t[k], target
            chain.append((k, t[k], target, w))
    return sorted(chain, key=lambda c: c[1])


def assign_units(fits, units):
    if not fits:
        return
    if len(fits) == 1:
        if units:
            fits[0].unit = units[0]
        return
    f1, f2 = fits[0], fits[1]
    s1, s2 = 1 / abs(f1.b), 1 / abs(f2.b)                # value per degree
    best = None
    for u1 in UNITS:
        for u2 in UNITS:
            if u1 == u2:
                continue
            err = abs(math.log(UNITS[u1] * s1 / (UNITS[u2] * s2)))
            seen = (u1 in units) + (u2 in units)
            key = (seen, -err)
            if err < 0.12 and (best is None or key > best[0]):
                best = (key, u1, u2)
    if best and best[0][0] >= 1:
        _, u1, u2 = best
        f1.unit, f2.unit = u1, u2
        f1.unit_inferred, f2.unit_inferred = u1 not in units, u2 not in units
    elif units:
        f1.unit = units[0]
    # hospital convention: kg/cm2 (or bar) is the primary scale when printed
    if f2.unit in ("kg/cm2", "bar") and f1.unit not in ("kg/cm2", "bar"):
        fits[0], fits[1] = f2, f1
