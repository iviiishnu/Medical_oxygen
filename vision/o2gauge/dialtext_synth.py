"""Synthetic dial faces WITH text ground truth, for the dial-text models (dialtext.py).

Every render is a random gauge: any range (0-1 ... 0-10000, vacuum, compound, decimals),
clockwise or counter-clockwise numbering, one or two printed scales (e.g. kg/cm2 + psi),
many fonts / colours / tick styles, unit + gas-name + brand words on the face, curved
gas-name text on a coloured bezel, a needle, neighbouring dials, glare, blur, low resolution.

It yields two kinds of training samples, made with EXACTLY the crop functions used at
inference (dialtext.dial_crop / dialtext.dial_strips):

  * detector samples: dial crop (512x512) or two unrolled bezel strips, + text mask
  * recogniser samples: one text item cropped from the same image, + its string
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .dialtext_geom import (CROP_S, DET_SIZE, STRIP_H, STRIP_R0, STRIP_R1, STRIP_SPAN, dial_crop,
                            dial_strips, rec_crop, shrink_box)

CANVAS = 1120
RC = 300.0                       # dial radius on the canvas
C0 = CANVAS / 2

FONT_FILES = ["arial.ttf", "arialbd.ttf", "bahnschrift.ttf", "calibri.ttf", "calibrib.ttf", "consola.ttf",
              "framd.ttf", "segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "tahoma.ttf", "tahomabd.ttf",
              "verdana.ttf", "verdanab.ttf", "times.ttf", "timesbd.ttf", "trebuc.ttf", "trebucbd.ttf",
              "micross.ttf", "Roboto-Regular.ttf", "corbel.ttf", "corbelb.ttf", "Candara.ttf", "Candarab.ttf",
              "georgia.ttf", "pala.ttf", "lucon.ttf", "ariblk.ttf", "impact.ttf", "cour.ttf", "courbd.ttf",
              "constan.ttf", "LeelawUI.ttf", "ebrima.ttf", "gadugi.ttf", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
              "LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"]
FONT_DIRS = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts", Path("/usr/share/fonts/truetype/dejavu"),
             Path("/usr/share/fonts/truetype/liberation"), Path("/usr/share/fonts/TTF")]


def _fonts() -> list[str]:
    out = []
    for f in FONT_FILES:
        for d in FONT_DIRS:
            if (d / f).exists():
                out.append(str(d / f))
                break
    if not out:
        raise RuntimeError("no TrueType fonts found for the dial-text generator")
    return out


FONTS = _fonts()
_font_cache: dict = {}


def font(path, size):
    k = (path, int(size))
    f = _font_cache.get(k)
    if f is None:
        f = ImageFont.truetype(path, int(size))
        if len(_font_cache) > 4000:
            _font_cache.clear()
        _font_cache[k] = f
    return f


# ----------------------------------------------------------------------------- scale tables
# (span, label steps)
SPANS = [(1, (0.1, 0.2)), (1.6, (0.2, 0.4)), (2.5, (0.5,)), (4, (0.5, 1)), (6, (1,)), (7, (1,)),
         (10, (1, 2)), (12, (2,)), (14, (2,)), (15, (3, 5)), (16, (2, 4)), (20, (2, 5)), (25, (5,)),
         (30, (5,)), (40, (5, 10)), (60, (10,)), (100, (10, 20)), (140, (20,)), (150, (25, 50)),
         (160, (20, 40)), (200, (20, 50)), (250, (50,)), (300, (50,)), (400, (50, 100)), (600, (100,)),
         (700, (100,)), (1000, (100, 200)), (1600, (200,)), (2500, (500,)), (3000, (500,)),
         (4000, (500, 1000)), (5000, (1000,)), (6000, (1000,)), (10000, (1000, 2000))]
VACUUM = [(-1, 0, 0.2), (-30, 0, 5), (-76, 0, 10), (-760, 0, 100), (-100, 0, 20), (-1, 0, 0.1)]
COMPOUND = [(-1, 3, 1), (-1, 5, 1), (-1, 9, 1), (-1, 1.5, 0.5), (-30, 60, 15), (-30, 30, 10)]
UNITS = {  # unit -> (kPa per unit, spellings)
    "kg/cm2": (98.0665, ["kg/cm2", "kg/cm2", "Kg/cm2", "kgf/cm2", "KG/CM2", "kg/cm\u00b2", "Kg/cm\u00b2"]),
    "bar": (100.0, ["bar", "BAR", "Bar"]),
    "psi": (6.89476, ["psi", "PSI", "Psi", "lb/in2"]),
    "kPa": (1.0, ["kPa", "KPa", "kpa"]),
    "MPa": (1000.0, ["MPa", "Mpa", "MPA"]),
    "mmHg": (0.133322, ["mmHg", "mm Hg", "MMHG"]),
    "cmHg": (1.33322, ["cmHg", "cm Hg"]),
    "inHg": (3.38639, ["inHg", "in Hg", "INHG"]),
}
GAS_NAMES = ["OXYGEN", "OXYGEN", "O2", "MEDICAL AIR", "AIR", "VACUUM", "NITROUS OXIDE", "N2O", "CO2",
             "CARBON DIOXIDE", "NITROGEN", "N2", "ARGON", "HELIUM", "SURGICAL AIR", "AGSS", "Oxygen", "Vacuum",
             "Medical Air", "Air"]
MISC_WORDS = ["USE NO OIL", "NO OIL", "CL 1.6", "CL 2.5", "Cl.1.6", "EN 837-1", "ISO 9001", "MADE IN INDIA",
              "OXYGEN USE NO OIL", "GLYCERINE", "SS316", "Class 1.0", "PRESSURE", "IP65", "R"]
BRANDS = ["VIGA", "RE", "WIKA", "BAUMER", "H GURU", "FIEBIG", "MANOMETER", "AIRGEN", "GENERAL", "ASHCROFT",
          "PRECISION", "WAAREE", "FORBES", "MEDIGAS", "SUPREME", "GAUGE CO", "VALMAX", "ZENITH"]


def nice(x):
    """Round to a 'printed-gauge' number (1, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 10 x 10^k)."""
    if x <= 0:
        return x
    e = 10 ** math.floor(math.log10(x))
    m = x / e
    for c in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 10):
        if m <= c * 1.04:
            return c * e
    return 10 * e


def fmt(v, step, style):
    if abs(v) < 1e-9:
        return "0" if style != "dec0" else ("0.0" if step < 1 else "0")
    if step < 1:
        d = max(1, -int(math.floor(math.log10(step) + 1e-9)))
        s = f"{v:.{d}f}"
        if style == "g":
            s = f"{v:g}"
        return s
    return f"{int(round(v))}"


@dataclass
class ScaleSpec:
    values: list            # label values
    texts: list             # label strings
    frac: list              # position along sweep 0..1
    unit: str
    color: tuple
    rho: float              # label centre radius (fraction of R)
    size: float             # cap height fraction of R
    font: str
    tick_r: tuple           # (r_in_major, r_out) fraction of R, or None for no ticks
    minor_per_label: int


@dataclass
class TextItem:
    text: str
    poly: np.ndarray        # 4x2 canvas coords (upright items) or None for arc items
    kind: str               # num / word / arc
    arc: tuple | None = None  # (angle0, angle1, r_in, r_out, upside_down) for arc text
    meta: dict = field(default_factory=dict)


# ----------------------------------------------------------------------------- dial rendering
def _ang_pt(a, r, c=(C0, C0)):
    t = math.radians(a)
    return c[0] + r * math.sin(t), c[1] - r * math.cos(t)


class DialRender:
    """One random gauge on a CANVAS x CANVAS image (dial centre at C0, radius RC)."""

    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        r = rng
        self.items: list[TextItem] = []
        self.dark_face = r.random() < 0.1
        face = (r.choice([(250, 250, 248), (245, 243, 232), (238, 238, 238), (252, 252, 252), (240, 236, 220),
                          (230, 236, 240)]) if not self.dark_face else (r.choice([(20, 20, 22), (30, 30, 45)])))
        if r.random() < 0.05 and not self.dark_face:
            face = (250, 225, 70)
        self.face = tuple(int(c + r.integers(-6, 7)) for c in face)
        self.ink = (int(r.integers(5, 45)),) * 3 if not self.dark_face else (240, 240, 240)
        self.sweep = float(r.choice([270, 270, 270, 270, 240, 260, 280, 300, 180, 220, 90]))
        self.start = (180 + (360 - self.sweep) / 2) % 360
        self.cw = r.random() > 0.15
        bg = np.array(r.integers(60, 230, 3), np.float32)
        img = np.empty((CANVAS, CANVAS, 3), np.float32)
        img[:] = bg
        img += np.linspace(-r.uniform(0, 30), r.uniform(0, 30), CANVAS, dtype=np.float32)[:, None, None]
        self.img = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
        self.d = ImageDraw.Draw(self.img)
        self.mask_up = Image.new("L", (CANVAS, CANVAS), 0)
        self.mask_arc = Image.new("L", (CANVAS, CANVAS), 0)
        self.boxes: list[tuple] = []          # occupied boxes (x0, y0, x1, y1)
        self._neighbours()
        self._bezel()
        self._scales()
        self._face_words()
        self._needle()

    # -- helpers
    def _font(self, bold=False):
        return str(self.rng.choice(FONTS))

    def _free(self, b, pad=4):
        x0, y0, x1, y1 = b
        return all(x1 + pad < c[0] or x0 - pad > c[2] or y1 + pad < c[1] or y0 - pad > c[3] for c in self.boxes)

    def _text(self, txt, cx, cy, fpath, cap, color, kind, check=True, draw=None, record=True):
        """Upright text centred at (cx, cy) with cap height `cap` px. Returns bbox or None."""
        f = font(fpath, max(6, cap * 1.38))
        x0, y0, x1, y1 = self.d.textbbox((0, 0), txt, font=f, anchor="lt")
        w, h = x1 - x0, y1 - y0
        bx = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        if check and not self._free(bx):
            return None
        (draw or self.d).text((cx - w / 2 - x0, cy - h / 2 - y0), txt, font=f, fill=color, anchor="lt")
        self.boxes.append(bx)
        if record:
            poly = np.array([[bx[0], bx[1]], [bx[2], bx[1]], [bx[2], bx[3]], [bx[0], bx[3]]], np.float64)
            self.items.append(TextItem(txt.replace("\u00b2", "2"), poly, kind))
            sb = shrink_box(bx)
            if sb is not None:
                ImageDraw.Draw(self.mask_up).rectangle(sb, fill=255)
        return bx

    def _neighbours(self):
        r = self.rng
        for _ in range(int(r.integers(0, 3))):
            a = r.uniform(0, 360)
            rr = RC * r.uniform(0.8, 1.2)
            dist = (1.65 + 1.15 * rr / RC + r.uniform(0, 0.4)) * RC
            c = _ang_pt(a, dist)
            col = tuple(int(t) for t in r.integers(0, 255, 3))
            self.d.ellipse((c[0] - rr * 1.15, c[1] - rr * 1.15, c[0] + rr * 1.15, c[1] + rr * 1.15), fill=col)
            self.d.ellipse((c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr), fill=(245, 245, 240))
            for k in range(int(r.integers(4, 9))):
                aa = 225 + k * 270 / 8
                p = _ang_pt(aa, rr * 0.72, c)
                self._text(str(int(r.integers(0, 400))), p[0], p[1], self._font(), rr * 0.12, (20, 20, 20), "num",
                           check=False)
        # random panel words / lamps
        for _ in range(int(r.integers(0, 4))):
            x, y = r.uniform(0, CANVAS), r.uniform(0, CANVAS)
            w = str(r.choice(GAS_NAMES + BRANDS + ["NORMAL", "LOW", "HIGH", "POWER", "MUTE", "TEST", "ALARM"]))
            cap = r.uniform(0.07, 0.16) * RC
            half_w = 0.45 * cap * len(w)
            # keep panel words off the dial and its bezel (drawn later on top)
            nx = min(max(C0, x - half_w), x + half_w)
            ny = min(max(C0, y - cap), y + cap)
            if math.dist((nx, ny), (C0, C0)) < 1.62 * RC:
                continue
            self._text(w, x, y, self._font(), cap, tuple(int(t) for t in r.integers(0, 90, 3)), "word")

    def _bezel(self):
        r = self.rng
        style = r.choice(["thin", "thin", "ring", "ring", "metal"])
        self.bezel_out = 1.06
        if style == "thin":
            col = tuple(int(t) for t in r.integers(20, 120, 3))
            self.d.ellipse(self._circ(r.uniform(1.04, 1.12)), fill=col)
            self.bezel_out = 1.1
        elif style == "metal":
            for k, rr in enumerate(np.linspace(1.18, 1.02, 6)):
                v = int(110 + 25 * k + r.integers(-10, 10))
                self.d.ellipse(self._circ(rr), fill=(v, v, v + 4))
            self.bezel_out = 1.18
        else:                                   # wide coloured ring with curved name text (Magnate style)
            ro = r.uniform(1.32, 1.55)
            col = r.choice([(245, 245, 245), (25, 25, 25), (20, 110, 50), (235, 190, 30), (30, 70, 160), (190, 30, 30)])
            col = tuple(int(c) for c in col)
            self.d.ellipse(self._circ(ro), fill=col)
            self.d.ellipse(self._circ(1.07), fill=(150, 150, 155))
            self.bezel_out = ro
            light = sum(col) > 380
            tcol = (20, 20, 20) if light else (245, 245, 245)
            if col == (20, 110, 50) or r.random() < 0.3:
                tcol = (20, 110, 50) if light else tcol
            name = str(r.choice(GAS_NAMES)).upper() if r.random() < 0.85 else str(r.choice(BRANDS))
            band = (1.07, ro)
            self._arc_text(name, band, top=True, color=tcol)
            if r.random() < 0.7:
                low = str(r.choice(["ISO 13485:2016 Certified.Co", "ISO 9001:2015", "MEDICAL GAS", "CE 0123",
                                    "Certified", str(r.choice(BRANDS))]))
                self._arc_text(low, band, top=False, color=tcol)
            if r.random() < 0.6:          # "CE" marks on the sides (rotated, not text we read)
                for a in (90, 270):
                    p = _ang_pt(a, (1.07 + ro) / 2 * RC)
                    f = font(self._font(), 0.1 * RC)
                    self.d.text(p, "CE", font=f, fill=tcol, anchor="mm")
        self.d.ellipse(self._circ(1.02), fill=self.face)

    def _circ(self, k, c=(C0, C0)):
        return (c[0] - k * RC, c[1] - k * RC, c[0] + k * RC, c[1] + k * RC)

    def _arc_text(self, txt, band, top, color):
        """Curved text centred at 12 o'clock (top) or 6 o'clock (bottom, readable from outside)."""
        r = self.rng
        r_in, r_out = band
        cap = (r_out - r_in) * RC * r.uniform(0.38, 0.6)
        rmid = (r_in + r_out) / 2 * RC
        f = font(self._font(), cap * 1.38)
        widths = [self.d.textlength(ch, font=f) for ch in txt]
        track = cap * r.uniform(0.0, 0.25)
        total = sum(widths) + track * (len(txt) - 1)
        span = math.degrees(total / rmid)
        if span > 170:
            return
        a = (-span / 2) if top else (180 + span / 2)
        for ch, w in zip(txt, widths):
            da = math.degrees((w / 2) / rmid)
            ac = a + da if top else a - da
            if ch != " ":
                pw = int(w + cap) + 4
                ph = int(cap * 2.2) + 4
                patch = Image.new("L", (pw, ph), 0)
                ImageDraw.Draw(patch).text((pw / 2, ph / 2), ch, font=f, fill=255, anchor="mm")
                rot = -ac if top else -(ac - 180)
                patch = patch.rotate(rot, resample=Image.BICUBIC, expand=True)
                p = _ang_pt(ac, rmid)
                pos = (int(p[0] - patch.width / 2), int(p[1] - patch.height / 2))
                self.img.paste(Image.new("RGB", patch.size, color), pos, patch)
            step = math.degrees((w + track) / rmid)
            a = a + step if top else a - step
        a0, a1 = (-span / 2, span / 2) if top else (180 - span / 2, 180 + span / 2)
        h = cap * 1.0
        ri, ro = (rmid - h / 2) / RC, (rmid + h / 2) / RC
        self.items.append(TextItem(txt, None, "arc", (a0, a1, ri, ro, not top)))
        # shrunk sector in the arc mask
        sh = 0.2 * h / RC
        sa = math.degrees(0.2 * h / rmid)
        self._sector(self.mask_arc, a0 + sa, a1 - sa, ri + sh, ro - sh)

    def _sector(self, m, a0, a1, ri, ro):
        pts = [_ang_pt(a, ro * RC) for a in np.linspace(a0, a1, 24)]
        pts += [_ang_pt(a, ri * RC) for a in np.linspace(a1, a0, 24)]
        ImageDraw.Draw(m).polygon(pts, fill=255)

    # -- scales
    def _make_values(self):
        r = self.rng
        u = r.random()
        if u < 0.1:
            lo, hi, st = VACUUM[int(r.integers(len(VACUUM)))]
            if r.random() < 0.5:             # printed as positive 0..760 etc
                lo, hi = 0, -lo
        elif u < 0.17:
            lo, hi, st = COMPOUND[int(r.integers(len(COMPOUND)))]
        else:
            span, steps = SPANS[int(r.integers(len(SPANS)))]
            lo, hi, st = 0, span, float(r.choice(steps))
            if r.random() < 0.04:
                lo = st
        vals = list(np.round(np.arange(lo, hi + st * 0.01, st), 6))
        if len(vals) > 13:
            st *= 2
            vals = list(np.round(np.arange(lo, hi + st * 0.01, st), 6))
        return lo, hi, st, vals

    def _scales(self):
        r = self.rng
        lo, hi, st, vals = self._make_values()
        unit = str(r.choice(list(UNITS)))
        if lo < 0 or hi in (76, 760, 30) and r.random() < 0.7:
            unit = str(r.choice(["bar", "mmHg", "cmHg", "inHg", "kPa", "kg/cm2"]))
        style = str(r.choice(["g", "g", "dec0"]))
        dual = r.random() < 0.3
        inside = r.random() < 0.7               # labels inside the tick ring
        size = r.uniform(0.075, 0.17) * (0.85 if dual else 1)
        if inside:
            tick = (0.80, 0.98) if not dual else (0.70, 0.82)
            rho = tick[0] - size * 0.9 - r.uniform(0.04, 0.1)
        else:
            tick = (0.62, 0.78)
            rho = tick[1] + size * 0.9 + r.uniform(0.05, 0.1)
        span = hi - lo
        frac = [(v - lo) / span for v in vals]
        texts = [fmt(v, st, style) for v in vals]
        drop = set()
        if r.random() < 0.15:
            drop.add(int(r.integers(0, len(vals))))
        keep = [i for i in range(len(vals)) if i not in drop]
        main = ScaleSpec([vals[i] for i in keep], [texts[i] for i in keep], [frac[i] for i in keep], unit,
                         self.ink, rho, size, self._font(), tick, int(r.choice([1, 2, 4, 5, 10])))
        self.scales = [main]
        self.lo, self.hi = lo, hi
        self._draw_scale(main, ticks=True, frac_all=frac)
        if dual:
            u2 = "psi" if unit in ("kg/cm2", "bar", "kPa", "MPa") else str(r.choice(["kPa", "bar", "psi"]))
            if u2 == unit:
                u2 = "kPa"
            f = UNITS[unit][0] / UNITS[u2][0]
            hi2 = nice(abs(hi) * f) if hi != 0 else nice(abs(lo) * f)
            lo2 = 0 if lo >= 0 else -nice(abs(lo) * f)
            if hi <= 0:
                hi2, lo2 = 0, -nice(abs(lo) * f)
            span2 = hi2 - lo2
            st2 = nice(span2 / r.choice([5, 6, 7, 8]))
            v2 = list(np.round(np.arange(lo2, hi2 + st2 * 0.01, st2), 6))
            # second scale shares the zero; its max angle follows the unit ratio
            k = (span2 / f) / span
            fr2 = [(v - lo2) / span2 * k for v in v2]
            pairs = [(v, fr) for v, fr in zip(v2, fr2) if fr <= 1.02]
            col = tuple(int(t) for t in r.choice([(180, 30, 30), (30, 60, 170), (20, 20, 20), (30, 130, 50)]))
            if self.dark_face:
                col = (240, 120, 120)
            if inside:   # second scale outside the first ticks
                rho2 = 0.82 + 0.06 + 0.11 * 0.9
                t2 = (0.82, 0.92)
            else:
                rho2 = rho - 0.2 - size
                t2 = None
            size2 = r.uniform(0.06, 0.11)
            sec = ScaleSpec([p[0] for p in pairs], [fmt(p[0], st2, "g") for p in pairs], [p[1] for p in pairs], u2,
                            col, min(rho2, 1.0), size2, self._font(), t2, 0)
            if len(pairs) >= 3:
                self.scales.append(sec)
                self._draw_scale(sec, ticks=t2 is not None, frac_all=None)

    def _angle(self, fr):
        return (self.start + fr * self.sweep) % 360 if self.cw else (self.start + self.sweep - fr * self.sweep) % 360

    def _draw_scale(self, s: ScaleSpec, ticks, frac_all):
        r = self.rng
        if ticks and s.tick_r:
            ti, to = s.tick_r
            lw = max(1, int(RC * r.uniform(0.006, 0.015)))
            if r.random() < 0.5:                # arc line
                rr = (to if r.random() < 0.5 else ti) * RC
                a0, a1 = (self.start, self.start + self.sweep)
                self.d.arc((C0 - rr, C0 - rr, C0 + rr, C0 + rr), a0 - 90, a1 - 90, fill=s.color, width=lw)
            if r.random() < 0.3:                # coloured band (red low, green normal)
                for c, f0, f1 in (((200, 40, 40), 0, 0.2), ((40, 160, 60), 0.2, 0.75)):
                    rr = (ti + 0.03) * RC
                    a0, a1 = self.start + f0 * self.sweep, self.start + f1 * self.sweep
                    self.d.arc((C0 - rr, C0 - rr, C0 + rr, C0 + rr), a0 - 90, a1 - 90, fill=c, width=int(0.04 * RC))
            fr_major = frac_all if frac_all is not None else s.frac
            n = max(1, s.minor_per_label)
            allf = sorted(set(np.round(np.concatenate([np.linspace(fr_major[i], fr_major[i + 1], n + 1)
                                                       for i in range(len(fr_major) - 1)]), 6)))
            for fr in allf:
                major = any(abs(fr - m) < 1e-5 for m in fr_major)
                a = self._angle(fr)
                p0 = _ang_pt(a, (ti if major else (ti + to) / 2) * RC)
                p1 = _ang_pt(a, to * RC)
                self.d.line([p0, p1], fill=s.color, width=lw * (2 if major else 1))
        for v, txt, fr in zip(s.values, s.texts, s.frac):
            a = self._angle(fr)
            p = _ang_pt(a, s.rho * RC)
            jit = r.normal(0, 0.01 * RC, 2)
            self._text(txt, p[0] + jit[0], p[1] + jit[1], s.font, s.size * RC, s.color, "num")

    def _face_words(self):
        r = self.rng
        slots = [(0, 0.38), (0, 0.52), (0, 0.66), (0, -0.4), (0, -0.55), (0, 0.25), (0, -0.25)]
        r.shuffle(slots)
        words = []
        u = UNITS[self.scales[0].unit][1]
        words.append(str(r.choice(u)))
        if len(self.scales) > 1:
            words.append(str(r.choice(UNITS[self.scales[1].unit][1])))
        if r.random() < 0.6:
            words.append(str(r.choice(GAS_NAMES)))
        for _ in range(int(r.integers(0, 3))):
            words.append(str(r.choice(MISC_WORDS + BRANDS)))
        for w, (sx, sy) in zip(words, slots):
            cap = r.uniform(0.06, 0.13) * RC
            col = self.ink if r.random() < 0.7 else tuple(int(t) for t in r.choice([(190, 30, 30), (30, 60, 160)]))
            self._text(w, C0 + sx * RC + r.normal(0, 0.03 * RC), C0 + sy * RC, self._font(), cap, col, "word")
        if r.random() < 0.4:                    # logo
            cx, cy = C0 + r.uniform(-0.15, 0.15) * RC, C0 + r.choice([-0.45, 0.6]) * RC
            w, h = r.uniform(0.25, 0.45) * RC, r.uniform(0.12, 0.25) * RC
            bx = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            if self._free(bx):
                col = tuple(int(t) for t in r.choice([(200, 40, 40), (20, 100, 60), (30, 60, 160)]))
                self.d.ellipse(bx, fill=col)
                self.boxes.append(bx)
                self._text(str(r.choice(BRANDS))[:5], cx, cy, self._font(), h * 0.45, (250, 250, 250), "word",
                           check=False)

    def _needle(self):
        r = self.rng
        self.value_frac = float(r.uniform(-0.02, 1.02))
        a = self._angle(min(max(self.value_frac, 0), 1))
        self.needle_angle = a
        L = r.uniform(0.7, 0.98) * RC
        tip = _ang_pt(a, L)
        self.needle_tip = tip
        tail = _ang_pt(a + 180, r.uniform(0.1, 0.25) * RC)
        w = r.uniform(0.012, 0.035) * RC
        col = tuple(int(t) for t in r.choice([(20, 20, 20), (200, 30, 30), (20, 40, 20), (30, 30, 30)]))
        if self.dark_face:
            col = (240, 240, 240) if r.random() < 0.5 else (230, 60, 40)
        perp = math.radians(a + 90)
        off = lambda p, k: (p[0] + k * math.sin(perp), p[1] - k * math.cos(perp))
        poly = [off(tail, w), off((C0, C0), w), off(tip, w * 0.15), off(tip, -w * 0.15), off((C0, C0), -w),
                off(tail, -w)]
        sh = [(x + 0.02 * RC, y + 0.03 * RC) for x, y in poly]
        ov = self.img.copy()
        ImageDraw.Draw(ov).polygon(sh, fill=(120, 120, 120))
        self.img = Image.blend(self.img, ov, 0.3)
        self.d = ImageDraw.Draw(self.img)
        self.d.polygon(poly, fill=col)
        hr = r.uniform(0.05, 0.11) * RC
        self.d.ellipse((C0 - hr, C0 - hr, C0 + hr, C0 + hr), fill=tuple(int(t) for t in r.integers(20, 200, 3)))


# ----------------------------------------------------------------------------- photo simulation
def _photo(render: DialRender, rng, r_photo=None):
    """Canvas -> camera photo of the dial. Returns (photo, H 3x3 canvas->photo, centre, radius, masks)."""
    r = rng
    rp = r_photo or float(np.exp(r.uniform(np.log(38), np.log(260))))
    s = rp / RC
    half = int(1.75 * rp) + 8
    Wp = Hp = 2 * half
    roll = r.uniform(-10, 10) if r.random() < 0.8 else r.uniform(-25, 25)
    A = cv2.getRotationMatrix2D((C0, C0), roll, s)
    A[:, 2] += np.array([half, half]) - np.array([C0, C0])
    H = np.vstack([A, [0, 0, 1]])
    if r.random() < 0.5:                       # mild perspective (camera not square-on)
        q = r.uniform(-0.12, 0.12, (4, 2)) * 0.5
        src = np.float32([[0, 0], [Wp, 0], [Wp, Hp], [0, Hp]])
        dst = (src + q * [Wp, Hp] * 0.25).astype(np.float32)
        H = cv2.getPerspectiveTransform(src, dst) @ H
    src = np.asarray(render.img)[:, :, ::-1]
    photo = cv2.warpPerspective(src, H, (Wp, Hp), flags=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_REPLICATE)
    if s < 0.5:                                 # proper anti-aliasing for strong down-scaling
        photo = cv2.warpPerspective(cv2.GaussianBlur(src, (0, 0), 0.45 / s), H, (Wp, Hp), flags=cv2.INTER_LINEAR,
                                    borderMode=cv2.BORDER_REPLICATE)
    mu = cv2.warpPerspective(np.asarray(render.mask_up), H, (Wp, Hp), flags=cv2.INTER_LINEAR)
    ma = cv2.warpPerspective(np.asarray(render.mask_arc), H, (Wp, Hp), flags=cv2.INTER_LINEAR)
    c = cv2.perspectiveTransform(np.float64([[[C0, C0]]]), H)[0, 0]
    edge = cv2.perspectiveTransform(np.float64([[[C0 + RC, C0], [C0, C0 + RC], [C0 - RC, C0], [C0, C0 - RC]]]), H)[0]
    rad = float(np.mean(np.linalg.norm(edge - c, axis=1)))
    return photo, H, (float(c[0]), float(c[1])), rad, mu, ma


def degrade(img, rng):
    r = rng
    f = img.astype(np.float32)
    f = f * r.uniform(0.6, 1.3) + r.uniform(-50, 40)
    f = f * (1 + r.uniform(-0.12, 0.12, 3))
    h, w = img.shape[:2]
    if r.random() < 0.5:                       # uneven light
        gx = np.linspace(-1, 1, w, dtype=np.float32)[None, :] * r.uniform(-40, 40)
        gy = np.linspace(-1, 1, h, dtype=np.float32)[:, None] * r.uniform(-40, 40)
        f += (gx + gy)[..., None]
    if r.random() < 0.55:                      # glass glare
        m = np.zeros((h, w), np.float32)
        for _ in range(int(r.integers(1, 4))):
            c = (int(r.uniform(0.1, 0.9) * w), int(r.uniform(0.1, 0.9) * h))
            ax = (int(r.uniform(0.03, 0.2) * w), int(r.uniform(0.01, 0.06) * h))
            cv2.ellipse(m, c, ax, float(r.uniform(0, 180)), 0, 360, 1.0, -1)
        k = int(max(w, h) * 0.03) | 1
        m = cv2.GaussianBlur(m, (k, k), 0)
        f = f + (255 - f) * m[..., None] * r.uniform(0.3, 0.9)
    img = np.clip(f, 0, 255).astype(np.uint8)
    sig = 0.0
    if r.random() < 0.5:
        sig = r.uniform(0.3, 1.6)
        img = cv2.GaussianBlur(img, (0, 0), sig)
    elif r.random() < 0.2:
        k = int(r.choice([3, 5, 7]))
        sig = k / 3
        ker = np.zeros((k, k), np.float32)
        ker[k // 2, :] = 1.0 / k
        M = cv2.getRotationMatrix2D((k / 2 - 0.5, k / 2 - 0.5), float(r.uniform(0, 180)), 1)
        ker = cv2.warpAffine(ker, M, (k, k))
        img = cv2.filter2D(img, -1, ker / max(ker.sum(), 1e-6))
    if r.random() < 0.6:
        img = np.clip(img.astype(np.float32) + r.normal(0, r.uniform(1, 8), img.shape), 0, 255).astype(np.uint8)
    if r.random() < 0.7:
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(r.integers(30, 92))])
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return img, sig


# ----------------------------------------------------------------------------- samples
@dataclass
class Scene:
    photo: np.ndarray
    center: tuple
    radius: float
    H: np.ndarray
    render: DialRender
    mask_up: np.ndarray
    mask_arc: np.ndarray
    blur: float = 0.0


def make_scene(rng, r_photo=None) -> Scene:
    rd = DialRender(rng)
    photo, H, c, rad, mu, ma = _photo(rd, rng, r_photo)
    img, sig = degrade(photo, rng)
    return Scene(img, c, rad, H, rd, mu, ma, sig)


def _poly_to_photo(sc: Scene, poly):
    return cv2.perspectiveTransform(poly[None].astype(np.float64), sc.H)[0]


def det_sample(sc: Scene, rng, strips: bool):
    """-> (image HxWx3 uint8, mask (H/2)x(W/2) float32 0/1, [(box_xyxy in image, text)])"""
    if strips:
        img, maps = dial_strips(sc.photo, *sc.center, sc.radius)
        m = cv2.remap(sc.mask_arc, maps[0], maps[1], cv2.INTER_LINEAR)
        # tile to 512 rows with more strips at jittered radii so batches have one shape
        rows, mrows = [img], [m]
        while sum(x.shape[0] for x in rows) < DET_SIZE:
            j = rng.uniform(0.9, 1.1)
            i2, mp2 = dial_strips(sc.photo, sc.center[0] + rng.normal(0, 0.02 * sc.radius),
                                  sc.center[1] + rng.normal(0, 0.02 * sc.radius), sc.radius * j)
            rows.append(i2)
            mrows.append(cv2.remap(sc.mask_arc, mp2[0], mp2[1], cv2.INTER_LINEAR))
        img = np.concatenate(rows)[:DET_SIZE]
        m = np.concatenate(mrows)[:DET_SIZE]
        boxes = []
        for it in sc.render.items:
            if it.kind != "arc":
                continue
            a0, a1, ri, ro, down = it.arc
            # strip coords (first two strips only), see dialtext_geom.dial_strips
            for k, is_down in ((0, False), (1, True)):
                if is_down != down:
                    continue
                if not is_down:
                    x0 = (a0 + STRIP_SPAN / 2) / STRIP_SPAN * DET_SIZE
                    x1 = (a1 + STRIP_SPAN / 2) / STRIP_SPAN * DET_SIZE
                    y0 = (STRIP_R1 - ro) / (STRIP_R1 - STRIP_R0) * STRIP_H
                    y1 = (STRIP_R1 - ri) / (STRIP_R1 - STRIP_R0) * STRIP_H
                else:
                    x0 = (180 + STRIP_SPAN / 2 - a1) / STRIP_SPAN * DET_SIZE
                    x1 = (180 + STRIP_SPAN / 2 - a0) / STRIP_SPAN * DET_SIZE
                    y0 = STRIP_H + (ri - STRIP_R0) / (STRIP_R1 - STRIP_R0) * STRIP_H
                    y1 = STRIP_H + (ro - STRIP_R0) / (STRIP_R1 - STRIP_R0) * STRIP_H
                boxes.append(((x0, y0, x1, y1), it.text))
        to_photo = (STRIP_R1 - STRIP_R0) * sc.radius / STRIP_H
    else:
        cx = sc.center[0] + rng.normal(0, 0.03 * sc.radius)
        cy = sc.center[1] + rng.normal(0, 0.03 * sc.radius)
        rr = sc.radius * rng.uniform(0.9, 1.1)
        img, M = dial_crop(sc.photo, cx, cy, rr)
        m = cv2.warpAffine(sc.mask_up, M, (DET_SIZE, DET_SIZE), flags=cv2.INTER_LINEAR)
        boxes = []
        for it in sc.render.items:
            if it.kind == "arc":
                continue
            p = _poly_to_photo(sc, it.poly)
            p = p @ M[:, :2].T + M[:, 2]
            x0, y0 = p.min(0)
            x1, y1 = p.max(0)
            if x1 < 0 or y1 < 0 or x0 > DET_SIZE or y0 > DET_SIZE:
                continue
            boxes.append(((x0, y0, x1, y1), it.text))
        to_photo = 1.0 / M[0, 0]
    if rng.random() < 0.15:                     # grayscale camera / IR
        img = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    m = cv2.resize(m, (img.shape[1] // 2, img.shape[0] // 2), interpolation=cv2.INTER_AREA)
    # legible = a person could read it in the photo: >= 7 px tall and not blurred away
    min_h = max(7.0, 4.5 * sc.blur) / to_photo
    boxes = [(b, t, (b[3] - b[1]) >= min_h) for b, t in boxes]
    return img, (m > 110).astype(np.float32), boxes


def rec_samples(img, boxes, rng, max_n=24):
    """Text crops (as at inference: box from the detector, padded) + strings. Illegible text skipped."""
    out = []
    for (x0, y0, x1, y1), txt, legible in boxes:
        h = y1 - y0
        w = x1 - x0
        if not legible or len(txt) > 22:
            continue
        if h < 5 or w < 3 or x0 < -0.3 * w or y0 < -0.3 * h or x1 > img.shape[1] + 0.3 * w or y1 > img.shape[0] + 0.3 * h:
            continue
        j = rng.normal(0, 0.07, 4) * h
        box = (x0 + j[0], y0 + j[1], x1 + j[2], y1 + j[3])
        crop = rec_crop(img, box)
        if crop is None:
            continue
        out.append((crop, txt))
        if len(out) >= max_n:
            break
    return out
