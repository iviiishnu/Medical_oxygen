"""Export frames + expected outputs so the Kotlin port can be verified against Python.

Writes contract/parity/<case>.png (lossless, so decoding is identical) and
contract/parity/expected.json. Run after any change to stage_a / lamps / imgops.

usage: python vision/tools/export_parity.py [--n 24]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from o2gauge.calibration import Calibration                 # noqa: E402
from o2gauge.geometry import point_at                        # noqa: E402
from o2gauge.lamps import read_lamps                         # noqa: E402
from o2gauge.stage_a import read_needle, polar_profile       # noqa: E402
from o2gauge.synth import (GAUGES, Layout, AugParams, augment, render_dial,  # noqa: E402
                           render_scene, calibration_from_gt)

ROOT = Path(__file__).resolve().parents[2]


def record(name, img, cal_dict, out_dir, truth=None):
    cal = Calibration.from_dict(cal_dict)
    cv2.imwrite(str(out_dir / f"{name}.png"), img)
    r = read_needle(img, cal)
    lamp_state, details = read_lamps(img, cal)
    prof, _ = polar_profile(img, cal)
    return {
        "file": f"{name}.png", "calibration": cal.to_dict(), "truth": truth,
        "value": r.value, "angle": r.angle, "confidence": r.confidence, "in_range": r.in_range,
        "reason": r.reason, "lamp_state": lamp_state,
        "lamp_scores": {k: {"colored": v["colored"], "core": v["core"]} for k, v in details.items()},
        "profile_sample": None if prof is None else [round(float(x), 6) for x in prof[::45]],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=24)
    a = ap.parse_args()
    out = ROOT / "contract" / "parity"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.png"):
        f.unlink()
    rng = np.random.default_rng(2026)
    cases = []
    for g in GAUGES:
        spec, lay = GAUGES[g], Layout()
        dial = render_dial(spec, lay, np.random.default_rng(9))
        _, gt0 = render_scene(spec, 0, lay, dial_cache=dial)
        cal = calibration_from_gt(gt0)
        for i in range(a.n // 2):
            v = float(rng.uniform(spec.min_value, spec.max_value))
            img, gt = render_scene(spec, v, lay, dial_cache=dial)
            if i % 2:
                img, _ = augment(img, gt, rng, AugParams(jpeg_p=0))
            cases.append(record(f"{g}_{i:02d}", img, cal, out, truth=round(v, 3)))
        # perspective case with rim points
        S = np.float32([[1, 0.05, 0], [0, 0.85, 36]])
        img, _ = render_scene(spec, spec.max_value * 0.37, lay, dial_cache=dial)
        img = cv2.warpAffine(img, S, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REPLICATE)
        def sq(p):
            return [float(p[0] + 0.05 * p[1]), float(0.85 * p[1] + 36)]
        c2 = dict(cal, center=sq(cal["center"]), zero_point=sq(cal["zero_point"]),
                  max_point=sq(cal["max_point"]),
                  rim_points=[sq(point_at(lay.cx, lay.cy, ang, lay.radius * 1.02)) for ang in range(0, 360, 30)])
        cases.append(record(f"{g}_perspective", img, c2, out, truth=round(spec.max_value * 0.37, 3)))
        # unreadable
        cases.append(record(f"{g}_blocked", np.full_like(img, 20), cal, out))
    # real photos, if present (samples/real/*.json written by the calibration tool)
    for cj in sorted((ROOT / "samples" / "real").glob("*.calibration.json")):
        img_path = cj.with_name(cj.name.replace(".calibration.json", ".jpg"))
        img = cv2.imread(str(img_path))
        if img is not None:
            cases.append(record(f"real_{img_path.stem}", img, json.loads(cj.read_text()), out))
    (out / "expected.json").write_text(json.dumps(cases, indent=1))
    print(f"wrote {len(cases)} parity cases to {out}")


if __name__ == "__main__":
    main()
