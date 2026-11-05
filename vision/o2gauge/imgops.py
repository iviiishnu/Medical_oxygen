"""Port-exact image operations.

Every function here has a line-by-line twin in android/.../vision/ImgOps.kt so the
tablet produces the same numbers as this Python reference. Only plain arithmetic is
used (no CLAHE / cv2.remap / cv2.resize, whose internals are hard to reproduce).
Images are uint8 BGR (OpenCV order) of shape (H, W, 3).
"""
from __future__ import annotations

import numpy as np


def to_gray(img: np.ndarray) -> np.ndarray:
    """Fixed-point BT.601 luma, identical to OpenCV's BGR2GRAY: float32 in [0,255]."""
    if img.ndim == 2:
        return img.astype(np.float32)
    b = img[..., 0].astype(np.int32)
    g = img[..., 1].astype(np.int32)
    r = img[..., 2].astype(np.int32)
    return ((r * 4899 + g * 9617 + b * 1868 + 8192) >> 14).astype(np.float32)


def box_blur(a: np.ndarray, k: int) -> np.ndarray:
    """Mean over a k x k window (k odd), reflect-101 borders, via an integral image."""
    r = k // 2
    if r == 0:
        return a.astype(np.float32)
    h, w = a.shape
    r_eff_y, r_eff_x = min(r, h - 1), min(r, w - 1)
    p = np.pad(a.astype(np.float64), ((r_eff_y, r_eff_y), (r_eff_x, r_eff_x)), mode="reflect")
    if r_eff_y < r or r_eff_x < r:                      # tiny image: fall back to edge padding
        p = np.pad(p, ((r - r_eff_y, r - r_eff_y), (r - r_eff_x, r - r_eff_x)), mode="edge")
    ii = np.zeros((p.shape[0] + 1, p.shape[1] + 1), np.float64)
    ii[1:, 1:] = p.cumsum(0).cumsum(1)
    s = ii[k:k + h, k:k + w] - ii[0:h, k:k + w] - ii[k:k + h, 0:w] + ii[0:h, 0:w]
    return (s / (k * k)).astype(np.float32)


def bilinear(a: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Sample a 2-D float array at float coords; samples outside the image are 0."""
    h, w = a.shape
    x0 = np.floor(xs).astype(np.int64)
    y0 = np.floor(ys).astype(np.int64)
    fx = (xs - x0).astype(np.float32)
    fy = (ys - y0).astype(np.float32)
    out = np.zeros(xs.shape, np.float32)
    inside = (x0 >= 0) & (y0 >= 0) & (x0 + 1 < w) & (y0 + 1 < h)
    xi, yi, fxi, fyi = x0[inside], y0[inside], fx[inside], fy[inside]
    v00 = a[yi, xi]
    v01 = a[yi, xi + 1]
    v10 = a[yi + 1, xi]
    v11 = a[yi + 1, xi + 1]
    out[inside] = (v00 * (1 - fxi) + v01 * fxi) * (1 - fyi) + (v10 * (1 - fxi) + v11 * fxi) * fyi
    return out


def hsv(img: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """OpenCV-convention HSV (H 0-179, S/V 0-255) computed in float, then rounded.
    Kotlin uses the same formula, so both agree exactly."""
    f = img.astype(np.float32)
    b, g, r = f[..., 0], f[..., 1], f[..., 2]
    v = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    d = v - mn
    s = np.where(v > 0, 255.0 * d / np.maximum(v, 1e-6), 0.0)
    dd = np.maximum(d, 1e-6)
    h = np.where(v == r, 60.0 * (g - b) / dd,
                 np.where(v == g, 120.0 + 60.0 * (b - r) / dd, 240.0 + 60.0 * (r - g) / dd))
    h = np.where(d == 0, 0.0, h)
    h = np.where(h < 0, h + 360.0, h)
    H = np.floor(h / 2.0 + 0.5).astype(np.int32) % 180
    S = np.floor(s + 0.5).astype(np.int32)
    V = v.astype(np.int32)
    return H, S, V


def grid_sample(a: np.ndarray, n: int = 64) -> np.ndarray:
    """Every k-th pixel on an n x n grid (cheap, exactly portable stand-in for a resize)."""
    h, w = a.shape[:2]
    ys = (np.arange(n) * h) // n
    xs = (np.arange(n) * w) // n
    return a[np.ix_(ys, xs)]
