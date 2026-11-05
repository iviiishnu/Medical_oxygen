"""Per-installation calibration (tapped once by staff, reused for every frame)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

from .geometry import Scale, dial_angle

LAMP_HUES = ("red", "green", "amber")


@dataclass
class Lamp:
    name: str                 # NORMAL / LOW / HIGH
    box: list[int]            # x, y, w, h in image pixels
    hue: str = "green"        # red | green | amber


@dataclass
class Calibration:
    center: list[float]
    radius: float
    zero_point: list[float]
    max_point: list[float]
    min_value: float = 0.0
    max_value: float = 16.0
    direction: str = "cw"
    unit: str = "kg/cm2"
    device_id: str = "tab-main-o2-01"
    gauge_id: str = "oxygen_main"
    image_size: list[int] | None = None
    rim_points: list[list[float]] | None = None   # >=5 points on the dial rim -> perspective fix
    needle_color: str = "dark"                    # dark | red
    needle_r_inner: float = 0.30                  # radial band (fraction of radius) used to find the needle
    needle_r_outer: float = 0.72
    lamps: list[Lamp] = field(default_factory=list)
    version: int = 1

    # ------------------------------------------------------------------ io
    @classmethod
    def from_dict(cls, d: dict) -> "Calibration":
        d = dict(d)
        lamps = [Lamp(**l) for l in d.pop("lamps", [])]
        known = set(cls.__dataclass_fields__)
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"unknown calibration keys: {sorted(unknown)}")
        cal = cls(**d, lamps=lamps)
        cal.validate()
        return cal

    @classmethod
    def load(cls, path: str | Path) -> "Calibration":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        self.validate()
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def validate(self) -> None:
        if self.radius <= 5:
            raise ValueError("radius too small")
        if self.max_value <= self.min_value:
            raise ValueError("max_value must be > min_value")
        if self.direction not in ("cw", "ccw"):
            raise ValueError("direction must be cw or ccw")
        if self.needle_color not in ("dark", "red"):
            raise ValueError("needle_color must be dark or red")
        if not 0 <= self.needle_r_inner < self.needle_r_outer <= 1.0:
            raise ValueError("need 0 <= needle_r_inner < needle_r_outer <= 1")
        for p in (self.zero_point, self.max_point):
            if np.hypot(p[0] - self.center[0], p[1] - self.center[1]) < 0.2 * self.radius:
                raise ValueError("zero/max mark too close to the centre - re-tap calibration")
        if abs(self.scale().sweep) < 30:
            raise ValueError("zero and max marks are almost at the same angle")
        names = [l.name for l in self.lamps]
        if len(names) != len(set(names)):
            raise ValueError("duplicate lamp names")
        for l in self.lamps:
            if l.hue not in LAMP_HUES:
                raise ValueError(f"lamp hue must be one of {LAMP_HUES}")
            if len(l.box) != 4 or l.box[2] <= 0 or l.box[3] <= 0:
                raise ValueError(f"bad lamp box for {l.name}")
        if self.rim_points is not None and len(self.rim_points) < 5:
            raise ValueError("rim_points needs at least 5 points (or omit it)")

    # ------------------------------------------------------------ geometry
    def scale(self) -> Scale:
        cx, cy = self.center
        return Scale(
            zero_angle=dial_angle(cx, cy, *self.zero_point),
            max_angle=dial_angle(cx, cy, *self.max_point),
            min_value=self.min_value,
            max_value=self.max_value,
            direction=self.direction,
        )

    def rectify_affine(self) -> np.ndarray | None:
        """2x3 affine that turns the (elliptical) dial in the image into a circle.

        None when no rim points were tapped (camera assumed square-on).
        """
        r = self.rectification()
        return None if r is None else r[0]

    def rectification(self) -> tuple[np.ndarray, float] | None:
        """(affine, rim radius in the rectified image) or None."""
        if not self.rim_points:
            return None
        import cv2

        pts = np.asarray(self.rim_points, dtype=np.float32)
        (ex, ey), (w, h), ang = cv2.fitEllipse(pts)
        if min(w, h) <= 0:
            return None
        big = max(w, h)
        t = np.radians(ang)
        u = np.array([np.cos(t), np.sin(t)])     # direction of the 'w' axis
        v = np.array([-np.sin(t), np.cos(t)])    # direction of the 'h' axis
        S = np.eye(2) + (big / w - 1) * np.outer(u, u) + (big / h - 1) * np.outer(v, v)
        c = np.array([ex, ey])
        M = np.zeros((2, 3))
        M[:, :2] = S
        M[:, 2] = c - S @ c
        return M, big / 2.0


def apply_affine(M: np.ndarray, p) -> list[float]:
    x, y = p
    return [float(M[0, 0] * x + M[0, 1] * y + M[0, 2]), float(M[1, 0] * x + M[1, 1] * y + M[1, 2])]
