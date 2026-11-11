"""Perspective correction of dials + digital-display pieces."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from o2gauge.auto import Dial, dial_rectifier, _warp_dial, dial_angle_pt   # noqa: E402
from o2gauge.digital import DIG_CHARS, encode_digits, NUM_RE              # noqa: E402
from o2gauge.digital_synth import random_value_text, render_digits, rec_sample, scene  # noqa: E402


def _dial_image(squash=0.8, rot=30.0):
    """A round dial with ticks every 30 deg, then squashed along a rotated axis (camera at an angle)."""
    S, c, R = 600, 300, 150
    img = np.full((S, S, 3), 120, np.uint8)
    cv2.circle(img, (c, c), R, (245, 245, 245), -1, cv2.LINE_AA)
    cv2.circle(img, (c, c), R, (20, 20, 20), 6, cv2.LINE_AA)
    for a in range(0, 360, 30):
        t = math.radians(a)
        p0 = (c + 0.8 * R * math.sin(t), c - 0.8 * R * math.cos(t))
        p1 = (c + 0.95 * R * math.sin(t), c - 0.95 * R * math.cos(t))
        cv2.line(img, tuple(int(v) for v in p0), tuple(int(v) for v in p1), (0, 0, 0), 3, cv2.LINE_AA)
    t = math.radians(rot)
    Rm = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
    A = Rm @ np.diag([1.0, squash]) @ Rm.T
    M = np.hstack([A, (np.array([c, c]) - A @ [c, c])[:, None]])
    return cv2.warpAffine(img, M, (S, S), borderValue=(120, 120, 120)), M, (c, c), R


SEEN = 70.0


def test_rectifier_recovers_angles():
    img, M, c, R = _dial_image(0.78, 25)
    true_pt = np.array([c[0] + 0.9 * R * math.sin(math.radians(SEEN)), c[1] - 0.9 * R * math.cos(math.radians(SEEN))])
    seen = M[:, :2] @ true_pt + M[:, 2]
    k = np.zeros((4, 3))
    k[0, :2] = c
    k[1, :2] = seen
    d = Dial(c, R * 0.9, 0.9, k)
    Mr, ratio = dial_rectifier(img, d)
    assert Mr is not None and 0.72 < ratio < 0.84
    dr = _warp_dial(d, Mr)
    raw = dial_angle_pt(c, seen)
    fixed = dial_angle_pt(dr.center, dr.kpts[1, :2])
    assert abs(raw - SEEN) > 4                       # the squash really moved the angle ...
    assert abs(fixed - SEEN) < 1.5                   # ... and the rectifier puts it back


def test_rectifier_leaves_round_dials_alone():
    img, _, c, R = _dial_image(1.0, 0)
    Mr, ratio = dial_rectifier(img, Dial(c, R, 0.9, np.zeros((4, 3))))
    assert Mr is None and ratio > 0.98


def test_digit_encoding_and_parse():
    assert encode_digits("-12.5") == [DIG_CHARS.index(ch) + 1 for ch in "-12.5"]
    assert NUM_RE.match("-0.85") and NUM_RE.match("120") and not NUM_RE.match("----") and not NUM_RE.match("1.2.3")


def test_synth_shapes():
    rng = np.random.default_rng(0)
    for _ in range(30):
        s = random_value_text(rng)
        assert s and all(ch in DIG_CHARS for ch in s)
        img, box, label, _ = render_digits(s, rng)
        assert img.dtype == np.uint8 and label == s
    bg = np.full((480, 640, 3), 90, np.uint8)
    im, q, lab = scene(rng, bg, 640)
    assert im.shape[1] == 640 and q.shape == (4, 2)
    x, lab = rec_sample(rng, bg)
    assert x.shape == (32, 192) and -1.01 <= x.min() and x.max() <= 1.01
