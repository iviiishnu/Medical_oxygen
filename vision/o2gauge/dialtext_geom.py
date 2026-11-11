"""Crops shared by the dial-text training generator and inference (keep them identical)."""
from __future__ import annotations

import math

import cv2
import numpy as np

DET_SIZE = 512          # detector input (dial crop) and strip width
CROP_S = 1.6            # dial crop covers centre +- CROP_S * radius
STRIP_SPAN = 200.0      # degrees of bezel unrolled per strip (top: -100..100, bottom: 80..280)
STRIP_R0, STRIP_R1 = 0.98, 1.68   # bezel band unrolled, fraction of the dial radius
STRIP_H = 96
SHRINK = 0.2            # detector target = text box shrunk by SHRINK * height on every side
REC_H, REC_W = 32, 192  # recogniser input

CHARS = "0123456789.-/:" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ" + "abcdefghijklmnopqrstuvwxyz" + " "
CHAR_IDX = {c: i + 1 for i, c in enumerate(CHARS)}   # 0 = CTC blank
MAX_LEN = 24


def encode_text(s: str) -> list[int]:
    s = s.replace("²", "2")
    return [CHAR_IDX[c] for c in s if c in CHAR_IDX][:MAX_LEN]


def dial_crop(img, cx, cy, r, s: float = CROP_S, size: int = DET_SIZE):
    """Square crop centred on the dial, dial radius -> size / (2 s). Returns (crop, M image->crop)."""
    k = size / (2 * s * r)
    M = np.float64([[k, 0, size / 2 - k * cx], [0, k, size / 2 - k * cy]])
    crop = cv2.warpAffine(img, M, (size, size), flags=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)
    return crop, M


def strip_maps(cx, cy, r):
    """Remap tables for the two unrolled bezel strips (top text reads left->right, bottom text too)."""
    xs = (np.arange(DET_SIZE, dtype=np.float64) + 0.5) / DET_SIZE * STRIP_SPAN
    ys = (np.arange(STRIP_H, dtype=np.float64) + 0.5) / STRIP_H
    a_top = np.radians(-STRIP_SPAN / 2 + xs)[None, :]
    rho_top = (STRIP_R1 - ys * (STRIP_R1 - STRIP_R0))[:, None] * r
    a_bot = np.radians(180 + STRIP_SPAN / 2 - xs)[None, :]
    rho_bot = (STRIP_R0 + ys * (STRIP_R1 - STRIP_R0))[:, None] * r
    mx = np.concatenate([cx + rho_top * np.sin(a_top), cx + rho_bot * np.sin(a_bot)])
    my = np.concatenate([cy - rho_top * np.cos(a_top), cy - rho_bot * np.cos(a_bot)])
    return mx.astype(np.float32), my.astype(np.float32)


def dial_strips(img, cx, cy, r):
    """(2*STRIP_H) x DET_SIZE image of the unrolled bezel ring above and below the dial."""
    mx, my = strip_maps(cx, cy, r)
    src = img
    px_per_strip_px = (STRIP_R1 - STRIP_R0) * r / STRIP_H
    if px_per_strip_px > 1.5:                       # big dial: pre-blur against aliasing
        src = cv2.GaussianBlur(img, (0, 0), 0.5 * px_per_strip_px)
    out = cv2.remap(src, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return out, (mx, my)


def shrink_box(b):
    x0, y0, x1, y1 = b
    h = y1 - y0
    d = SHRINK * h
    dx = min(d, max(0.0, (x1 - x0) / 2 - 1))
    if h - 2 * d < 1:
        return None
    return (x0 + dx, y0 + d, x1 - dx, y1 - d)


def unclip(x0, y0, x1, y1):
    """Inverse of shrink_box for a detected component (same pixel space)."""
    hs = y1 - y0
    h = hs / (1 - 2 * SHRINK)
    d = SHRINK * h
    return (x0 - d, y0 - d, x1 + d, y1 + d)


def rec_crop(img, box):
    """Text box -> REC_H x REC_W grayscale float32 in [-1, 1] (text left-aligned, right padding)."""
    x0, y0, x1, y1 = box
    h, w = y1 - y0, x1 - x0
    if h < 3 or w < 2:
        return None
    m = 0.12 * h
    x0, y0, x1, y1 = x0 - m, y0 - m, x1 + m, y1 + m
    h, w = y1 - y0, x1 - x0
    tw = int(round(min(REC_W, max(8, w / h * REC_H))))
    k = (REC_H / h, tw / w)
    M = np.float64([[k[1], 0, -k[1] * x0], [0, k[0], -k[0] * y0]])
    g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if min(k) < 0.7:
        g = cv2.GaussianBlur(g, (0, 0), 0.4 / min(k))
    c = cv2.warpAffine(g, M, (tw, REC_H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    lo, hi = np.percentile(c, 2), np.percentile(c, 98)
    c = (c - lo) / max(hi - lo, 8.0)
    c = np.clip(c, 0, 1)
    if np.median(c) < 0.5:                       # light text on dark: make all text dark-on-light
        c = 1 - c
    out = np.ones((REC_H, REC_W), np.float32) * float(np.median(c[:, -2:]))
    out[:, :tw] = c
    return out * 2 - 1


def dial_angle(cx, cy, px, py):
    return math.degrees(math.atan2(px - cx, -(py - cy))) % 360.0
