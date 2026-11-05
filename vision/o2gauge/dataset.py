"""Model-input crops + YOLO-pose labels.

The tablet never feeds the whole camera frame to the model. It crops a square
around the calibrated dial (side = 2 * CROP_SCALE * radius), resizes to IMGSZ,
and maps the 4 predicted keypoints back. Training uses the same crop with random
jitter (scale, shift, rotation, perspective) so small camera movement or an
imperfect calibration tap does not hurt.

Keypoint order (YOLO kpt index): 0 centre, 1 needle tip, 2 zero mark, 3 max mark.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

IMGSZ = 320
CROP_SCALE = 1.4
KPT_NAMES = ["center", "tip", "zero", "max"]


def crop_box(cx: float, cy: float, radius: float, scale: float = CROP_SCALE) -> tuple[float, float, float]:
    """(x0, y0, side) of the square crop."""
    side = 2 * scale * radius
    return cx - side / 2, cy - side / 2, side


def crop_affine(cx, cy, radius, scale=CROP_SCALE, rot_deg=0.0, dx=0.0, dy=0.0, size=IMGSZ) -> np.ndarray:
    """2x3 affine mapping image -> model input (size x size). dx, dy in crop fractions."""
    side = 2 * scale * radius
    s = size / side
    a = math.radians(rot_deg)
    ca, sa = math.cos(a) * s, math.sin(a) * s
    # rotate/scale about the dial centre, then put the (shifted) centre in the middle
    tx = size / 2 + dx * size - (ca * cx - sa * cy)
    ty = size / 2 + dy * size - (sa * cx + ca * cy)
    return np.array([[ca, -sa, tx], [sa, ca, ty]], np.float64)


def warp_points(M: np.ndarray, pts) -> np.ndarray:
    p = np.asarray(pts, np.float64).reshape(-1, 2)
    return p @ M[:, :2].T + M[:, 2]


def make_crop(img: np.ndarray, M: np.ndarray, size: int = IMGSZ) -> np.ndarray:
    return cv2.warpAffine(img, M, (size, size), flags=cv2.INTER_AREA if M[0, 0] < 1 else cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)


def yolo_pose_label(kpts: np.ndarray, radius_px: float, size: int = IMGSZ) -> str:
    """One line: class cx cy w h  (x y v)*4, normalised. Box = dial face (centre +- 1.1 R)."""
    c = kpts[0]
    half = 1.1 * radius_px
    x0, y0 = max(0.0, c[0] - half), max(0.0, c[1] - half)
    x1, y1 = min(size, c[0] + half), min(size, c[1] + half)
    parts = [0, (x0 + x1) / 2 / size, (y0 + y1) / 2 / size, (x1 - x0) / size, (y1 - y0) / size]
    for x, y in kpts:
        v = 2 if (0 <= x < size and 0 <= y < size) else 0
        parts += [x / size if v else 0.0, y / size if v else 0.0, v]
    return " ".join(f"{p:.6f}" if isinstance(p, float) else str(p) for p in parts)
