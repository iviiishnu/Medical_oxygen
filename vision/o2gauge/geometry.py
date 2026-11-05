"""Angle <-> value maths shared by Stage A, Stage B and the Android port.

Convention (used everywhere, including Kotlin):
  * Image coordinates: x to the right, y DOWN.
  * "Dial angle" = degrees measured CLOCKWISE from 12 o'clock, in [0, 360).
      12 o'clock = 0, 3 o'clock = 90, 6 o'clock = 180, 9 o'clock = 270.
  * The scale runs clockwise from the zero mark to the max mark
    (true for both hospital oxygen gauges). Counter-clockwise gauges
    (e.g. vacuum) set direction = "ccw".
"""
from __future__ import annotations

import math
from dataclasses import dataclass

EDGE_TOL_DEG = 4.0   # how far past the 0 / max marks still counts as "on the scale"


def dial_angle(cx: float, cy: float, px: float, py: float) -> float:
    """Clockwise angle from 12 o'clock of point p around centre c, in [0, 360)."""
    a = math.degrees(math.atan2(px - cx, -(py - cy)))
    return a % 360.0


def point_at(cx: float, cy: float, angle_deg: float, r: float) -> tuple[float, float]:
    """Inverse of dial_angle: point at radius r and dial angle."""
    t = math.radians(angle_deg)
    return cx + r * math.sin(t), cy - r * math.cos(t)


@dataclass(frozen=True)
class Scale:
    zero_angle: float      # dial angle of the min mark
    max_angle: float       # dial angle of the max mark
    min_value: float = 0.0
    max_value: float = 16.0
    direction: str = "cw"  # "cw" or "ccw"

    @property
    def sweep(self) -> float:
        """Angular length of the printed scale (0, 360]."""
        if self.direction == "cw":
            s = (self.max_angle - self.zero_angle) % 360.0
        else:
            s = (self.zero_angle - self.max_angle) % 360.0
        return s if s > 1e-9 else 360.0

    def rel(self, angle: float) -> float:
        """Angle travelled from the zero mark in the scale direction, [0, 360)."""
        if self.direction == "cw":
            return (angle - self.zero_angle) % 360.0
        return (self.zero_angle - angle) % 360.0

    def value(self, angle: float, edge_tol: float = EDGE_TOL_DEG) -> tuple[float, bool]:
        """Map a needle angle to a value.

        Returns (value, in_range). Angles inside the dead gap at the bottom of
        the dial are clamped to the nearer end. Within `edge_tol` degrees of
        either end (needle resting on the stop pin, tap error) the reading is
        still in range; deeper into the gap it is flagged in_range=False.
        """
        rel = self.rel(angle)
        sweep = self.sweep
        if rel <= sweep:
            frac = rel / sweep
            in_range = True
        else:
            gap = 360.0 - sweep
            past_max = rel - sweep
            before_zero = 360.0 - rel
            if past_max < gap / 2.0:
                frac, in_range = 1.0, past_max <= edge_tol
            else:
                frac, in_range = 0.0, before_zero <= edge_tol
        return self.min_value + frac * (self.max_value - self.min_value), in_range

    def angle(self, value: float) -> float:
        """Dial angle for a value (used by the synthetic generator)."""
        frac = (value - self.min_value) / (self.max_value - self.min_value)
        d = frac * self.sweep
        if self.direction == "cw":
            return (self.zero_angle + d) % 360.0
        return (self.zero_angle - d) % 360.0


def value_from_keypoints(center, tip, zero, maxp, min_value, max_value, direction="cw"):
    """Stage B post-processing: 4 keypoints -> value. Identical to the Kotlin port."""
    cx, cy = center
    scale = Scale(
        zero_angle=dial_angle(cx, cy, *zero),
        max_angle=dial_angle(cx, cy, *maxp),
        min_value=min_value,
        max_value=max_value,
        direction=direction,
    )
    return scale.value(dial_angle(cx, cy, *tip))
