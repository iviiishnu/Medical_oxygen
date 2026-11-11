"""Synthetic digital (seven-segment LCD / LED) pressure displays for training the digital reader.

Every call draws a fresh random display:
  * LCD (dark segments on grey / green / blue / amber backlight, faint "ghost" unlit segments) or
    LED (red / green / blue / white / amber lit segments with glow on black)
  * 2-6 digits, decimal point, minus sign, leading blanks, italic slant, segment thickness / gaps
  * unit label (bar, psi, kPa, MPa, kg/cm2, ...) and small status icons beside the digits
  * the display sits in a meter body (rounded box or round digital gauge), pasted into a real
    background photo with a random camera angle (perspective), scale, glare, blur, noise, JPEG.

Outputs
  scene(rng, bg)  -> (image BGR, digit-area quad (4,2) in image px, text)      detector training
  rec_sample(rng) -> (crop gray float [-1,1] REC_H x REC_W, text)              recogniser training
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from .dialtext_geom import REC_H, REC_W, rec_crop

#   aaa
#  f   b
#   ggg
#  e   c
#   ddd
SEGS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc",
        "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g", " ": ""}
SEVEN_ALT = {"7": "fabc", "9": "abcfg", "6": "fgedc"}        # other common shapes (7 with f, 9 w/o tail)
UNITS = ["bar", "psi", "kPa", "MPa", "kg/cm2", "kgf/cm2", "mbar", "inHg", "mmHg", "%", "", "", ""]
LCD_BG = [(170, 185, 165), (150, 175, 160), (200, 200, 190), (210, 190, 120), (230, 175, 90), (110, 180, 120),
          (190, 200, 205), (90, 160, 200), (60, 170, 235), (90, 200, 240), (110, 210, 225)]  # BGR (last 3 orange/yellow)
LED_COL = [(40, 40, 255), (60, 255, 80), (255, 160, 40), (240, 240, 240), (40, 190, 255), (230, 230, 120)]


def random_value_text(rng) -> str:
    """A reading as a gauge would show it (digits + optional '.' / '-'), no padding blanks."""
    kind = rng.random()
    if kind < 0.45:                                      # x.xx / xx.x / xxx.x pressure style
        ndec = int(rng.choice([1, 1, 2, 2, 3]))
        mag = float(rng.choice([1, 10, 100, 1000])) * rng.random()
        s = f"{mag:.{ndec}f}"
    elif kind < 0.7:                                     # integer
        s = str(int(rng.integers(0, 10 ** int(rng.integers(1, 5)))))
    elif kind < 0.82:                                    # negative (vacuum)
        s = f"-{rng.random() * float(rng.choice([1, 10, 100, 1000])):.{int(rng.integers(0, 3))}f}"
    elif kind < 0.9:                                     # leading zero decimals 0.05
        s = f"0.{int(rng.integers(0, 1000)):03d}"[: int(rng.integers(3, 6))]
    else:                                                # dashes / zeros (sensor idle / overrange)
        s = str(rng.choice(["----", "--", "0", "00", "0.0", "0.00", "8888", "88.88", "-1"]))
    s = s.rstrip(".")
    digits = sum(ch.isdigit() or ch == "-" for ch in s)
    if digits > 6:
        s = s[: s.index(".")] if "." in s and s.index(".") <= 6 else s[:6]
    return s or "0"


def _seg_polys(w, h, t, gap):
    """Segment polygons in a w x h cell (origin top-left), hexagonal segment ends."""
    m = t / 2
    def hseg(y):
        return np.float32([[m + gap, y], [m + gap + m, y - m], [w - m - gap - m, y - m], [w - m - gap, y],
                           [w - m - gap - m, y + m], [m + gap + m, y + m]])
    def vseg(x, y0, y1):
        return np.float32([[x, y0 + gap], [x + m, y0 + gap + m], [x + m, y1 - gap - m], [x, y1 - gap],
                           [x - m, y1 - gap - m], [x - m, y0 + gap + m]])
    hm = h / 2
    return {"a": hseg(m), "g": hseg(hm), "d": hseg(h - m),
            "f": vseg(m, m, hm), "b": vseg(w - m, m, hm), "e": vseg(m, hm, h - m), "c": vseg(w - m, hm, h - m)}


def render_digits(text: str, rng, ndig: int | None = None, scale: float = 1.0):
    """-> (BGR display image, digit-area box (x0,y0,x1,y1) in it, label text, style dict).
    The label is what a person reads (blanks dropped)."""
    lcd = rng.random() < 0.6
    dh = int(rng.integers(36, 90) * scale)                       # digit height px
    dw = int(dh * rng.uniform(0.45, 0.62))
    t = max(2.0, dh * rng.uniform(0.09, 0.17))
    gap = t * rng.uniform(0.06, 0.25)
    pitch = dw + int(dh * rng.uniform(0.12, 0.3))
    slant = math.radians(rng.uniform(0, 11)) if rng.random() < 0.7 else 0.0
    chars = [c for c in text if c != "."]
    dots = set()
    k = -1
    for c in text:
        if c == ".":
            dots.add(k)
        else:
            k += 1
    n = len(chars)
    ndig = max(n, ndig or n + int(rng.integers(0, 3) if rng.random() < 0.5 else 0))
    lead = ndig - n                                              # right-aligned like real meters
    pad_x, pad_y = int(dh * rng.uniform(0.25, 0.6)), int(dh * rng.uniform(0.2, 0.45))
    unit = str(rng.choice(UNITS))
    unit_w = int(dh * 0.55 * len(unit) * 0.6) + (int(dh * 0.3) if unit else 0)
    W = pad_x * 2 + ndig * pitch + int(dh * math.tan(slant)) + unit_w
    H = pad_y * 2 + dh + (int(dh * 0.35) if rng.random() < 0.3 else 0)
    if lcd:
        bg = np.array(LCD_BG[int(rng.integers(len(LCD_BG)))], np.float32) * rng.uniform(0.75, 1.1)
        on = np.array([25, 25, 25], np.float32) + rng.uniform(0, 35)
        ghost = rng.uniform(0.0, 0.18) if rng.random() < 0.7 else 0.0
    else:
        bg = np.array([rng.uniform(5, 40)] * 3, np.float32) + rng.uniform(-5, 10, 3)
        on = np.array(LED_COL[int(rng.integers(len(LED_COL)))], np.float32)
        ghost = rng.uniform(0.0, 0.12) if rng.random() < 0.5 else 0.0
    bg = np.clip(bg, 0, 255)
    img = np.zeros((H, W, 3), np.float32) + bg
    # gentle backlight gradient
    gy = np.linspace(rng.uniform(0.85, 1.0), rng.uniform(0.95, 1.12), H)[:, None, None]
    gx = np.linspace(rng.uniform(0.9, 1.05), rng.uniform(0.9, 1.05), W)[None, :, None]
    img *= gy * gx
    mask_on = np.zeros((H, W), np.float32)
    mask_ghost = np.zeros((H, W), np.float32)
    shear = np.float32([[1, -math.tan(slant)], [0, 1]])
    x0 = pad_x + int(dh * math.tan(slant))
    y0 = pad_y
    alt = rng.random() < 0.3
    for i in range(ndig):
        c = " " if i < lead else chars[i - lead]
        lit = SEVEN_ALT.get(c, SEGS[c]) if alt else SEGS[c]
        polys = _seg_polys(dw, dh, t, gap)
        for name, p in polys.items():
            q = (p - [0, dh]) @ shear.T + [x0 + i * pitch, y0 + dh]
            target = mask_on if name in lit else mask_ghost
            cv2.fillPoly(target, [np.round(q * 8).astype(np.int32)], 1.0, cv2.LINE_AA, shift=3)
        # decimal point after this digit (also drawn as ghost on many LCDs)
        dp_c = (x0 + i * pitch + dw + (pitch - dw) * 0.45 - 0.0 * dh, y0 + dh - t * 0.5)
        rad = max(1.5, t * 0.6)
        di = i - lead
        if di >= 0 and di in dots:
            cv2.circle(mask_on, (int(dp_c[0] * 8), int(dp_c[1] * 8)), int(rad * 8), 1.0, -1, cv2.LINE_AA, shift=3)
        elif rng.random() < 0.5:
            cv2.circle(mask_ghost, (int(dp_c[0] * 8), int(dp_c[1] * 8)), int(rad * 8), 1.0, -1, cv2.LINE_AA, shift=3)
    mask_on = np.maximum(mask_on, mask_on * 0)
    if lcd:
        a = np.clip(mask_on + ghost * mask_ghost, 0, 1)[..., None]
        img = img * (1 - a) + on * a
        if rng.random() < 0.5:                                    # LCD segment shadow on the glass
            sh = cv2.GaussianBlur(mask_on, (0, 0), 1.2)
            sh = np.roll(sh, (int(rng.integers(1, 4)), int(rng.integers(1, 4))), (0, 1))[..., None]
            img = img * (1 - 0.15 * sh)
    else:
        glow = cv2.GaussianBlur(mask_on, (0, 0), max(1.0, t * rng.uniform(0.4, 1.2)))[..., None]
        a = np.clip(mask_on + ghost * mask_ghost, 0, 1)[..., None]
        img = img * (1 - a) + on * a + on * glow * rng.uniform(0.2, 0.6)
        core = mask_on[..., None] * rng.uniform(0.0, 0.5)              # blown-out core
        img = img * (1 - core) + 255 * core
    img = np.clip(img, 0, 255).astype(np.uint8)
    # unit label
    col = tuple(float(v) for v in np.clip(on, 0, 255))
    if unit:
        fs = dh / 60.0 * rng.uniform(0.45, 0.65)
        ux = pad_x + ndig * pitch + int(dh * math.tan(slant)) + int(dh * 0.15)
        uy = y0 + dh if rng.random() < 0.6 else y0 + int(dh * 0.45)
        cv2.putText(img, unit, (ux, uy), cv2.FONT_HERSHEY_SIMPLEX, fs, col, max(1, int(fs * 2)), cv2.LINE_AA)
    # small icons / bar graph above or below
    if rng.random() < 0.35:
        for j in range(int(rng.integers(1, 4))):
            cx = int(rng.uniform(pad_x, W - pad_x))
            cv2.rectangle(img, (cx, 3), (cx + int(dh * 0.25), 3 + int(dh * 0.12)), col, -1)
    box = (x0 - int(dh * math.tan(slant)) - 2, y0 - 2, x0 + ndig * pitch - int((pitch - dw) * 0.3) + 2, y0 + dh + 2)
    if not dots or max(dots) < len(chars) - 1:
        pass
    label = text
    return img, box, label, {"lcd": lcd, "dh": dh}


def _body(display, rng):
    """Put the display in a meter body. -> (body BGR, alpha 0..1, offset of display in body)."""
    h, w = display.shape[:2]
    round_body = rng.random() < 0.45
    if round_body:
        R = int(max(w, h) * rng.uniform(0.62, 0.85))
        S = 2 * R + 8
        body = np.zeros((S, S, 3), np.uint8)
        alpha = np.zeros((S, S), np.float32)
        col = np.array([rng.uniform(20, 240)] * 3) + rng.uniform(-20, 20, 3)
        cv2.circle(body, (S // 2, S // 2), R, tuple(float(c) for c in np.clip(col, 0, 255)), -1, cv2.LINE_AA)
        cv2.circle(alpha, (S // 2, S // 2), R, 1.0, -1, cv2.LINE_AA)
        rim = tuple(float(c) for c in np.clip(col * rng.uniform(0.5, 1.4), 0, 255))
        cv2.circle(body, (S // 2, S // 2), R, rim, max(2, R // 14), cv2.LINE_AA)
        ox, oy = (S - w) // 2, int((S - h) // 2 + rng.uniform(-0.15, 0.1) * R)
        # some labels / buttons on the face
        for _ in range(int(rng.integers(0, 3))):
            bx = int(S / 2 + rng.uniform(-0.4, 0.4) * R)
            by = int(oy + h + rng.uniform(0.1, 0.35) * R)
            cv2.circle(body, (bx, by), max(3, R // 12), tuple(float(c) for c in rng.uniform(30, 220, 3)), -1, cv2.LINE_AA)
        if rng.random() < 0.6:
            cv2.putText(body, str(rng.choice(["DIGITAL", "PRESSURE", "O2", "OXYGEN", "bar", "MPa", "GAUGE"])),
                        (int(S / 2 - 0.35 * R), int(oy - 0.12 * R)), cv2.FONT_HERSHEY_SIMPLEX, R / 160,
                        tuple(float(c) for c in rng.uniform(0, 255, 3)), max(1, R // 80), cv2.LINE_AA)
    else:
        mx, my = int(w * rng.uniform(0.08, 0.5)), int(h * rng.uniform(0.15, 0.9))
        Wb, Hb = w + 2 * mx, h + my + int(h * rng.uniform(0.15, 1.2))
        body = np.zeros((Hb, Wb, 3), np.uint8)
        alpha = np.zeros((Hb, Wb), np.float32)
        col = np.array([rng.uniform(20, 240)] * 3) + rng.uniform(-25, 25, 3)
        rad = int(min(Wb, Hb) * rng.uniform(0.02, 0.2))
        for a_, c_ in ((alpha, 1.0), (body, tuple(float(c) for c in np.clip(col, 0, 255)))):
            cv2.rectangle(a_, (rad, 0), (Wb - rad, Hb), c_, -1)
            cv2.rectangle(a_, (0, rad), (Wb, Hb - rad), c_, -1)
            for cx, cy in ((rad, rad), (Wb - rad, rad), (rad, Hb - rad), (Wb - rad, Hb - rad)):
                cv2.circle(a_, (cx, cy), rad, c_, -1, cv2.LINE_AA)
        ox, oy = mx, my
        for _ in range(int(rng.integers(0, 4))):                     # buttons
            bx = int(rng.uniform(0.1, 0.9) * Wb)
            by = int(oy + h + rng.uniform(0.1, 0.8) * (Hb - oy - h))
            if by < Hb - 4:
                cv2.circle(body, (bx, by), max(3, int(h * 0.12)), tuple(float(c) for c in rng.uniform(30, 220, 3)), -1, cv2.LINE_AA)
    # dark frame around the window
    f = max(1, int(min(h, w) * rng.uniform(0.0, 0.06)))
    cv2.rectangle(body, (ox - f, oy - f), (ox + w + f, oy + h + f), tuple(float(c) for c in rng.uniform(0, 60, 3)), -1)
    body[oy:oy + h, ox:ox + w] = display
    return body, alpha, (ox, oy)


def _camera(img, rng):
    if rng.random() < 0.5:
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.3, 2.0))
    if rng.random() < 0.3:                                             # motion blur
        k = int(rng.integers(3, 9))
        ker = np.zeros((k, k), np.float32)
        ker[k // 2] = 1.0 / k
        M = cv2.getRotationMatrix2D((k / 2 - 0.5, k / 2 - 0.5), rng.uniform(0, 180), 1)
        img = cv2.filter2D(img, -1, cv2.warpAffine(ker, M, (k, k)))
    f = img.astype(np.float32)
    f = f * rng.uniform(0.55, 1.35) + rng.uniform(-35, 25)
    if rng.random() < 0.6:
        f += rng.normal(0, rng.uniform(1, 10), f.shape)
    if rng.random() < 0.35:                                            # glare blob
        H, W = f.shape[:2]
        cx, cy = rng.uniform(0, W), rng.uniform(0, H)
        yy, xx = np.mgrid[:H, :W]
        s = rng.uniform(0.05, 0.3) * max(H, W)
        f += rng.uniform(60, 200) * np.exp(-(((xx - cx) ** 2) + ((yy - cy) ** 2) * rng.uniform(0.3, 3)) / (2 * s * s))[..., None]
    img = np.clip(f, 0, 255).astype(np.uint8)
    if rng.random() < 0.6:
        q = int(rng.integers(25, 90))
        img = cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)
    return img


def scene(rng, bg, max_side: int = 960):
    """Paste a random digital meter into background `bg` (BGR) at a random camera angle.
    -> (image, quad (4,2) of the digit area in image px, label)."""
    text = random_value_text(rng)
    disp, box, label, _ = render_digits(text, rng)
    body, alpha, (ox, oy) = _body(disp, rng)
    H, W = bg.shape[:2]
    s = max_side / max(H, W)
    bg = cv2.resize(bg, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    H, W = bg.shape[:2]
    bh, bw = body.shape[:2]
    target = rng.uniform(0.15, 0.75) * min(H, W)                       # body size in the scene
    k = target / max(bh, bw)
    # camera angle: perspective by moving the corners, plus in-plane rotation
    src = np.float32([[0, 0], [bw, 0], [bw, bh], [0, bh]])
    yaw, pitch = rng.uniform(-0.45, 0.45), rng.uniform(-0.4, 0.4)
    rot = math.radians(rng.normal(0, 8) if rng.random() < 0.85 else rng.uniform(-35, 35))
    cxy = np.float32([bw / 2, bh / 2])
    dst = []
    for (x, y) in src:
        dx, dy = x - cxy[0], y - cxy[1]
        zf = 1 + yaw * dx / bw + pitch * dy / bh                      # nearer side looks bigger
        dx, dy = dx * zf, dy * zf
        dx, dy = dx * math.cos(rot) - dy * math.sin(rot), dx * math.sin(rot) + dy * math.cos(rot)
        dst.append([dx * k, dy * k])
    dst = np.float32(dst)
    span = dst.max(0) - dst.min(0)
    px = rng.uniform(-dst.min(0)[0], max(-dst.min(0)[0] + 1, W - dst.max(0)[0]))
    py = rng.uniform(-dst.min(0)[1], max(-dst.min(0)[1] + 1, H - dst.max(0)[1]))
    dst += [px, py]
    P = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(body, P, (W, H), flags=cv2.INTER_LINEAR)
    a = cv2.warpPerspective(alpha, P, (W, H), flags=cv2.INTER_LINEAR)[..., None]
    if rng.random() < 0.6:                                             # soft drop shadow
        sh = cv2.GaussianBlur(a, (0, 0), max(1.0, 0.02 * span.max()))
        sh = np.roll(sh, (int(rng.integers(0, 12)), int(rng.integers(0, 12))), (0, 1))
        sh = sh[..., None] if sh.ndim == 2 else sh
        bg = (bg * (1 - 0.4 * sh)).astype(np.uint8)
    out = (bg * (1 - a) + warped * a).astype(np.uint8)
    out = _camera(out, rng)
    x0, y0, x1, y1 = box
    q = np.float32([[x0 + ox, y0 + oy], [x1 + ox, y0 + oy], [x1 + ox, y1 + oy], [x0 + ox, y1 + oy]])
    q = cv2.perspectiveTransform(q[None], P)[0]
    return out, q, label


def multi_scene(rng, bg, max_side: int = 960, big: bool = False):
    """A display with 1-3 stacked number rows (one LCD window, like monitors / panel meters), optionally
    filling most of the frame (camera close to the meter). -> (image, [quads], [labels])"""
    nrows = int(rng.integers(1, 4))
    lcd_bg = np.array(LCD_BG[int(rng.integers(len(LCD_BG)))], np.float32) * rng.uniform(0.8, 1.1)
    rows, boxes, labels = [], [], []
    for _ in range(nrows):
        for _try in range(20):
            disp, box, label, st = render_digits(random_value_text(rng), rng, scale=rng.uniform(0.7, 1.4))
            if st["lcd"]:
                break
        rows.append((disp, box))
        labels.append(label)
    W = max(d.shape[1] for d, _ in rows) + int(rng.integers(0, 120))
    gap = int(rng.integers(0, 25))
    H = sum(d.shape[0] for d, _ in rows) + gap * (nrows - 1)
    win = np.zeros((H, W, 3), np.uint8)
    win[:] = np.clip(lcd_bg, 0, 255).astype(np.uint8)
    y = 0
    for d, (x0, y0, x1, y1) in rows:
        ox = W - d.shape[1] if rng.random() < 0.7 else 0                 # numbers right-aligned
        # blend the row's own backlight into the shared window
        win[y:y + d.shape[0], ox:ox + d.shape[1]] = d
        boxes.append((x0 + ox, y0 + y, x1 + ox, y1 + y))
        y += d.shape[0] + gap
    body, alpha, (bx, by) = _body(win, rng)
    Hb, Wb = bg.shape[:2]
    s = max_side / max(Hb, Wb)
    bg = cv2.resize(bg, (int(Wb * s), int(Hb * s)), interpolation=cv2.INTER_AREA)
    Hb, Wb = bg.shape[:2]
    bh, bw = body.shape[:2]
    target = (rng.uniform(0.6, 1.3) if big else rng.uniform(0.2, 0.7)) * min(Hb, Wb)
    k = target / max(bh, bw)
    src = np.float32([[0, 0], [bw, 0], [bw, bh], [0, bh]])
    d = rng.uniform(-0.08, 0.08, (4, 2)) * [bw, bh]
    rot = math.radians(rng.normal(0, 5))
    c = np.float32([bw / 2, bh / 2])
    dst = []
    for (x, y_), (ddx, ddy) in zip(src, d):
        dx, dy = x + ddx - c[0], y_ + ddy - c[1]
        dst.append([(dx * math.cos(rot) - dy * math.sin(rot)) * k, (dx * math.sin(rot) + dy * math.cos(rot)) * k])
    dst = np.float32(dst)
    lo, hi = dst.min(0), dst.max(0)
    px = rng.uniform(-lo[0], max(-lo[0] + 1, Wb - hi[0])) if hi[0] - lo[0] < Wb else Wb / 2
    py = rng.uniform(-lo[1], max(-lo[1] + 1, Hb - hi[1])) if hi[1] - lo[1] < Hb else Hb / 2
    dst += [px, py]
    P = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(body, P, (Wb, Hb))
    a = cv2.warpPerspective(alpha, P, (Wb, Hb))[..., None]
    out = _camera((bg * (1 - a) + warped * a).astype(np.uint8), rng)
    quads = []
    for x0, y0, x1, y1 in boxes:
        q = np.float32([[x0 + bx, y0 + by], [x1 + bx, y0 + by], [x1 + bx, y1 + by], [x0 + bx, y1 + by]])
        quads.append(cv2.perspectiveTransform(q[None], P)[0])
    return out, quads, labels


def quad_crop(img, quad, out_h=64, jitter=None, rng=None):
    """Rectify the digit-area quad to an upright strip (height out_h). Optional box jitter
    (simulates detector error)."""
    q = np.float32(quad).copy()
    w = max(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3]))
    h = max(np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1]))
    if jitter and rng is not None:
        u = (q[1] - q[0]) / max(w, 1)
        v = (q[3] - q[0]) / max(h, 1)
        dl, dr = rng.uniform(-jitter, jitter * 1.5, 2) * h
        dt, db = rng.uniform(-jitter, jitter, 2) * h
        q[0] += -dl * u - dt * v
        q[3] += -dl * u + db * v
        q[1] += dr * u - dt * v
        q[2] += dr * u + db * v
        w = max(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3]))
        h = max(np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1]))
    ow = int(round(out_h * w / max(h, 1)))
    ow = max(8, min(ow, out_h * 12))
    M = cv2.getPerspectiveTransform(q, np.float32([[0, 0], [ow, 0], [ow, out_h], [0, out_h]]))
    return cv2.warpPerspective(img, M, (ow, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def rec_from_strip(strip):
    """Upright digit strip (BGR) -> recogniser input (REC_H x REC_W, [-1,1]) via the shared rec_crop."""
    h, w = strip.shape[:2]
    m = 0.12 * h
    return rec_crop(strip, (m, m, w - m, h - m))


def rec_sample(rng, bg=None):
    """One recogniser training sample: (input REC_H x REC_W float32 [-1,1], label)."""
    if bg is None or rng.random() < 0.4:
        text = random_value_text(rng)
        disp, box, label, _ = render_digits(text, rng, scale=rng.uniform(0.35, 1.0))
        x0, y0, x1, y1 = box
        quad = np.float32([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
        # mild perspective on the display alone
        h, w = disp.shape[:2]
        d = rng.uniform(-0.06, 0.06, (4, 2)) * [w, h]
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        P = cv2.getPerspectiveTransform(src, (src + d).astype(np.float32))
        disp = cv2.warpPerspective(disp, P, (w, h), borderMode=cv2.BORDER_REPLICATE)
        quad = cv2.perspectiveTransform(quad[None], P)[0]
        img = _camera(disp, rng)
    else:
        img, quad, label = scene(rng, bg, max_side=int(rng.integers(480, 1100)))
    if rng.random() < 0.6:
        # what the detector actually gives at run time: the UPRIGHT box around the (slanted) digit area
        (x0, y0), (x1, y1) = quad.min(0), quad.max(0)
        quad = np.float32([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    strip = quad_crop(img, quad, 48, jitter=0.12, rng=rng)
    x = rec_from_strip(strip)
    return x, label
