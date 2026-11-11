"""Build samples/demo/: a ready set of photos for a live demo of the tester app.

  01-03  the real panel photos as taken
  04-05  the Magnate panel seen from a different camera angle (re-projected, 25-30 deg)
  06     alarm box with the needle moved to 2.6 kg/cm2 and the lamp switched to red  -> ABNORMAL
  07     Magnate with the oxygen needle moved to 7.5 kg/cm2                          -> NORMAL, reads 7.5
  08-09  digital pressure meters (synthetic seven-segment, pasted into real photos)

usage: python vision/tools/make_demo_set.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vision"))
sys.path.insert(0, str(ROOT / "vision/tools"))
from eval_angles import turn                                 # noqa: E402
from eval_auto import full_with_value, set_lamps             # noqa: E402
from o2gauge.digital_synth import render_digits, _body       # noqa: E402
from o2gauge.photo_synth import load_photo_dial              # noqa: E402

OUT = ROOT / "samples/demo"


def digital_meter(bg, text, seed, where=(0.62, 0.55), size=0.42):
    """A clean, upright digital gauge (LCD) pasted onto a real photo - like a camera pointed at it."""
    rng = np.random.default_rng(seed)
    for _ in range(50):
        disp, box, label, st = render_digits(text, rng, scale=1.3)
        if st["lcd"]:
            break
    body, alpha, _ = _body(disp, rng)
    H, W = bg.shape[:2]
    k = size * min(H, W) / max(body.shape[:2])
    body = cv2.resize(body, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    alpha = cv2.resize(alpha, None, fx=k, fy=k)[..., None]
    h, w = body.shape[:2]
    x0, y0 = int(where[0] * W - w / 2), int(where[1] * H - h / 2)
    roi = bg[y0:y0 + h, x0:x0 + w].astype(np.float32)
    bg = bg.copy()
    bg[y0:y0 + h, x0:x0 + w] = (roi * (1 - alpha) + body * alpha).astype(np.uint8)
    return bg


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    real = ROOT / "samples/real"
    shutil.copy(real / "magnate.jpg", OUT / "01_magnate_panel.jpg")
    shutil.copy(real / "alarm_box.jpg", OUT / "02_alarm_box.jpg")
    mag = cv2.imread(str(real / "magnate.jpg"))
    cv2.imwrite(str(OUT / "03_magnate_turned_left_25deg.jpg"), turn(mag, -25, 0))
    cv2.imwrite(str(OUT / "04_magnate_from_below_30deg.jpg"), turn(mag, 0, 30))
    cv2.imwrite(str(OUT / "05_magnate_turned_right_35deg.jpg"), turn(mag, 35, 0))
    ab = load_photo_dial(real / "alarm_box")
    low = set_lamps(full_with_value("alarm_box", ab, 2.6), "red")
    cv2.imwrite(str(OUT / "06_alarm_box_LOW_2.6_red_lamp.jpg"), low)
    mg = load_photo_dial(real / "magnate")
    cv2.imwrite(str(OUT / "07_magnate_oxygen_7.5.jpg"), full_with_value("magnate", mg, 7.5))
    wall = cv2.imread(str(real / "alarm_box.jpg"))
    cv2.imwrite(str(OUT / "08_digital_meter_4.82.jpg"), digital_meter(wall, "4.82", 3, where=(0.2, 0.75), size=0.35))
    # a digital meter on its own (plain wall): the verdict then comes from the display alone
    yy, xx = np.mgrid[:900, :1200]
    plain = np.dstack([200 - 0.03 * yy + 0.01 * xx] * 3).astype(np.float32) + np.random.default_rng(1).normal(0, 3, (900, 1200, 3))
    plain = np.clip(plain * [0.95, 1.0, 1.02], 0, 255).astype(np.uint8)
    cv2.imwrite(str(OUT / "09_digital_meter_LOW_2.95.jpg"), digital_meter(plain, "2.95", 11, where=(0.5, 0.5), size=0.5))
    for p in sorted(OUT.glob("*.jpg")):
        print(p.name)


if __name__ == "__main__":
    main()
