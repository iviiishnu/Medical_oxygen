"""Photo-based synthetic generator: real dial photo -> unlimited labelled images.

1. needle mask from <photo>.needle.json (hub, tip, tail, widths)
2. clean dial = inpaint(photo, mask)            (the needle "removed")
3. needle sprite = photo pixels inside the mask with a soft alpha matte
   (alpha from how much darker each pixel is than the clean dial, so the
   original background around the needle is NOT carried along)
4. render(value): rotate the sprite about the hub to that value's angle and
   composite it onto the clean dial -> exact keypoints for free.
Produces the same ground-truth dict as synth.render_scene().
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np

from .calibration import Calibration
from .geometry import dial_angle
from .imgops import to_gray, hsv


def _needle_polygon(n: dict) -> np.ndarray:
    hx, hy = n["hub"]
    tx, ty = n["tip"]
    ax, ay = n["tail"]
    ang = math.atan2(ty - hy, tx - hx)
    px, py = -math.sin(ang), math.cos(ang)            # unit perpendicular
    def off(x, y, w):
        return (x + px * w / 2, y + py * w / 2), (x - px * w / 2, y - py * w / 2)
    t1, t2 = off(tx, ty, n["width_tip"])
    h1, h2 = off(hx, hy, n["width_hub"])
    a1, a2 = off(ax, ay, n["width_tail"])
    return np.array([t1, h1, a1, a2, h2, t2], np.float32)


class PhotoDial:
    ROI_SCALE = 2.6   # work on a square of +-ROI_SCALE*radius around the dial (speed); lamps outside are dropped

    def __init__(self, image_path: str | Path, cal: Calibration, needle: dict, name: str | None = None):
        self.name = name or Path(image_path).stem
        full = cv2.imread(str(image_path))
        if full is None:
            raise FileNotFoundError(image_path)
        H0, W0 = full.shape[:2]
        r = int(cal.radius * self.ROI_SCALE)
        x0 = max(0, int(cal.center[0]) - r)
        y0 = max(0, int(cal.center[1]) - r)
        x1 = min(W0, int(cal.center[0]) + r)
        y1 = min(H0, int(cal.center[1]) + r)
        self.offset = (x0, y0)
        self.img = full[y0:y1, x0:x1].copy()

        def sh(p):
            return [float(p[0]) - x0, float(p[1]) - y0]
        d = cal.to_dict()
        d.update(center=sh(cal.center), zero_point=sh(cal.zero_point), max_point=sh(cal.max_point),
                 image_size=[x1 - x0, y1 - y0],
                 rim_points=[sh(p) for p in cal.rim_points] if cal.rim_points else None,
                 lamps=[{**l, "box": [l["box"][0] - x0, l["box"][1] - y0, l["box"][2], l["box"][3]]}
                        for l in d["lamps"]
                        if l["box"][0] >= x0 and l["box"][1] >= y0
                        and l["box"][0] + l["box"][2] <= x1 and l["box"][1] + l["box"][3] <= y1])
        self.cal = Calibration.from_dict(d)
        needle = dict(needle)
        for k in ("hub", "tip", "tail"):
            needle[k] = sh(needle[k])
        self.n = needle
        H, W = self.img.shape[:2]
        mask = np.zeros((H, W), np.uint8)
        poly = _needle_polygon(needle)
        cv2.fillPoly(mask, [np.round(poly).astype(np.int32)], 255, cv2.LINE_AA)
        cv2.circle(mask, tuple(int(round(v)) for v in needle["hub"]), int(needle["hub_radius"]), 255, -1, cv2.LINE_AA)
        # the needle's shadow on the dial face: same shape shifted by a fixed offset (fixed light),
        # so it is cut out and moved together with the needle
        sdx, sdy = needle.get("shadow_offset", [0, 0])
        if sdx or sdy:
            sh = np.zeros_like(mask)
            cv2.fillPoly(sh, [np.round(poly + [sdx, sdy]).astype(np.int32)], 255, cv2.LINE_AA)
            hub_s = (int(round(needle["hub"][0] + sdx)), int(round(needle["hub"][1] + sdy)))
            cv2.circle(sh, hub_s, int(needle["hub_radius"]), 255, -1, cv2.LINE_AA)
            # fill the gap between needle and shadow
            k = int(max(abs(sdx), abs(sdy))) * 2 + 1
            mask = cv2.morphologyEx(cv2.max(mask, sh), cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
        self.mask = mask
        big = cv2.dilate(mask, np.ones((9, 9), np.uint8))
        method = cv2.INPAINT_NS if needle.get("inpaint", "telea") == "ns" else cv2.INPAINT_TELEA
        self.clean = cv2.inpaint(self.img, big, int(needle.get("inpaint_radius", 9)), method)
        # soft alpha matte: darker-than-background pixels inside the (dilated) mask
        L_orig = to_gray(self.img)
        L_clean = to_gray(self.clean)
        inside = big > 0
        dark = np.percentile(L_orig[mask > 0], 10)
        diff = L_clean - L_orig
        denom = max(float(np.median(L_clean[inside]) - dark), 20.0)
        alpha = np.clip(diff / denom * 1.4, 0, 1) * inside
        _, S, V = hsv(self.img)
        alpha[(S > 90) & (V > 60)] = 0.0                    # coloured print (logo) is not needle
        # the hub cap belongs to the needle assembly regardless of brightness (highlights)
        hub = np.zeros((H, W), np.uint8)
        cv2.circle(hub, tuple(int(round(v)) for v in needle["hub"]), int(needle["hub_radius"]), 255, -1)
        alpha = np.maximum(alpha, (hub > 0) * 1.0)
        alpha = cv2.GaussianBlur(alpha.astype(np.float32), (3, 3), 0)
        self.alpha = alpha
        self.orig_angle = dial_angle(*needle["hub"], *needle["tip"])
        self.scale = cal.scale()

    def lamp_boxes(self):
        return [{"name": l.name, "hue": l.hue, "box": list(l.box)} for l in self.cal.lamps]

    def render(self, value: float):
        v = float(np.clip(value, self.cal.min_value, self.cal.max_value))
        a_new = self.scale.angle(v)
        rot = a_new - self.orig_angle                      # clockwise degrees
        hx, hy = self.n["hub"]
        M = cv2.getRotationMatrix2D((hx, hy), -rot, 1.0)   # OpenCV: positive = counter-clockwise
        H, W = self.img.shape[:2]
        spr = cv2.warpAffine(self.img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        a = cv2.warpAffine(self.alpha, M, (W, H), flags=cv2.INTER_LINEAR)[..., None]
        out = (self.clean.astype(np.float32) * (1 - a) + spr.astype(np.float32) * a).astype(np.uint8)
        tx, ty = self.n["tip"]
        tip = [float(M[0, 0] * tx + M[0, 1] * ty + M[0, 2]), float(M[1, 0] * tx + M[1, 1] * ty + M[1, 2])]
        gt = {
            "gauge": self.name, "value": v, "angle": a_new,
            "center": [float(hx), float(hy)], "radius": float(self.cal.radius), "tip": tip,
            "zero": list(map(float, self.cal.zero_point)), "max": list(map(float, self.cal.max_point)),
            "lamps": self.lamp_boxes(), "lamp_state": "AS_PHOTOGRAPHED",
            "min_value": self.cal.min_value, "max_value": self.cal.max_value,
        }
        return out, gt

    def debug_sheet(self) -> np.ndarray:
        """Mask overlay | clean dial | three re-rendered values, around the dial."""
        cx, cy = self.n["hub"]
        r = int(self.cal.radius * 1.5)
        def cut(im):
            x0, y0 = int(cx - r), int(cy - r)
            return cv2.resize(im[max(0, y0):y0 + 2 * r, max(0, x0):x0 + 2 * r], (300, 300))
        ov = self.img.copy()
        ov[self.mask > 0] = (0.5 * ov[self.mask > 0] + [0, 0, 127]).astype(np.uint8)
        tiles = [cut(ov), cut(self.clean)]
        span = self.cal.max_value - self.cal.min_value
        for f in (0.05, 0.5, 0.95):
            im, gt = self.render(self.cal.min_value + f * span)
            im = im.copy()
            cv2.circle(im, tuple(int(v) for v in gt["tip"]), 4, (255, 0, 255), -1)
            tiles.append(cut(im))
        return np.hstack(tiles)


def load_photo_dial(stem: str | Path) -> PhotoDial:
    """stem = samples/real/alarm_box -> uses .jpg, .calibration.json, .needle.json"""
    stem = Path(stem)
    cal = Calibration.load(f"{stem}.calibration.json")
    needle = json.loads(Path(f"{stem}.needle.json").read_text())
    return PhotoDial(f"{stem}.jpg", cal, needle, stem.name)
