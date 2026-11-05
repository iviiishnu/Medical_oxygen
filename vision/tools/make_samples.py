"""Generate stand-in panel photos + their calibration for demos and tests.
Replace with Babu sir's real photos when available (same folder layout).

usage: python vision/tools/make_samples.py [--out samples]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from o2gauge.synth import GAUGES, Layout, render_dial, render_scene, add_glare, calibration_from_gt  # noqa: E402

CASES = {"alarm_box_16": [5.4, 4.0, 3.2, 2.5, 12.0], "magnate_10": [5.4, 4.2, 3.0, 1.5, 8.0]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="samples")
    a = ap.parse_args()
    for g, values in CASES.items():
        spec, lay = GAUGES[g], Layout()
        d = Path(a.out) / g
        d.mkdir(parents=True, exist_ok=True)
        dial = render_dial(spec, lay, np.random.default_rng(7))
        truth = {}
        for v in values:
            img, gt = render_scene(spec, v, lay, dial_cache=dial)
            name = f"{g}_{v:05.2f}.jpg"
            cv2.imwrite(str(d / name), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            truth[name] = {"value": v, "lamp_state": gt["lamp_state"]}
        img, gt = render_scene(spec, values[0], lay, dial_cache=dial)
        img = add_glare(img, np.random.default_rng(3), strength=0.8,
                        center=(int(lay.cx + 40), int(lay.cy - 60)))
        name = f"{g}_{values[0]:05.2f}_glare.jpg"
        cv2.imwrite(str(d / name), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        truth[name] = {"value": values[0], "lamp_state": gt["lamp_state"]}
        (d / "calibration.json").write_text(json.dumps(calibration_from_gt(gt), indent=2))
        (d / "truth.json").write_text(json.dumps(truth, indent=2))
        print("wrote", d)


if __name__ == "__main__":
    main()
