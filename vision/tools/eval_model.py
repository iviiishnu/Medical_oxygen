"""Accuracy report: Stage A, Stage B and fusion on held-out frames rendered from the REAL
panel photos (new seed, full camera frames, glare/blur/noise), plus the two original photos.

usage: python vision/tools/eval_model.py --model vision/models/gauge_pose.pt [--n 200] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from o2gauge.config import MonitorConfig                    # noqa: E402
from o2gauge.fusion import fuse                             # noqa: E402
from o2gauge.photo_synth import load_photo_dial             # noqa: E402
from o2gauge.stage_a import read_needle                     # noqa: E402
from o2gauge.stage_b import KeypointReader                  # noqa: E402
from o2gauge.synth import AugParams, augment                # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EYE_READING = {"alarm_box": 4.75, "magnate": 4.45}          # read by eye from the photos (+-0.1)


def stats(errs):
    e = np.asarray([x for x in errs if x is not None], float)
    if len(e) == 0:
        return {"n": 0}
    return {"n": int(len(e)), "mean": round(float(e.mean()), 4), "p95": round(float(np.percentile(e, 95)), 4),
            "worst": round(float(e.max()), 4), "within_0.2": round(float((e <= 0.2).mean()), 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "vision" / "models" / "gauge_pose.pt"))
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--json", default=None)
    ap.add_argument("--cal-marks", action="store_true", help="use tapped zero/max instead of predicted")
    a = ap.parse_args()
    cfg = MonitorConfig.load()
    kb = KeypointReader(a.model, use_cal_marks=a.cal_marks)
    report = {"model": Path(a.model).name, "per_gauge": {}, "real_photos": {}}
    for stem in ("alarm_box", "magnate"):
        d = load_photo_dial(ROOT / "samples" / "real" / stem)
        cal = d.cal
        rng = np.random.default_rng(777)
        ea, eb, ef, unsure, tb = [], [], [], 0, []
        worst = None
        for _ in range(a.n):
            v = float(rng.uniform(cal.min_value, cal.max_value))
            img, gt = d.render(v)
            img, _ = augment(img, gt, rng, AugParams(persp=0.004, glare_p=0.5, blur_p=0.4, noise_p=0.5, jpeg_p=0.7))
            ra = read_needle(img, cal)
            t0 = time.perf_counter()
            rb = kb(img, cal)
            tb.append((time.perf_counter() - t0) * 1000)
            f = fuse(ra, rb, "NORMAL" if v >= cfg.low_threshold else "LOW", cfg)
            ea.append(abs(ra.value - v) if ra.value is not None and ra.confidence >= cfg.min_confidence else None)
            eb.append(abs(rb.value - v) if rb.value is not None and rb.confidence >= cfg.min_confidence else None)
            if f.status == "UNCERTAIN":
                unsure += 1
                ef.append(None)
            else:
                e = abs(f.value - v)
                ef.append(e)
                if worst is None or e > worst[0]:
                    worst = (round(e, 3), round(v, 3), ra.value, rb.value)
        report["per_gauge"][stem] = {
            "stage_a": stats(ea), "stage_b": stats(eb), "fused": stats(ef),
            "fused_uncertain_frames": unsure, "fused_worst(err,true,A,B)": worst,
            "stage_b_ms_median": round(float(np.median(tb)), 1),
        }
        import cv2
        from o2gauge.calibration import Calibration
        full_cal = Calibration.load(ROOT / "samples" / "real" / f"{stem}.calibration.json")
        img = cv2.imread(str(ROOT / "samples" / "real" / f"{stem}.jpg"))
        ra, rb = read_needle(img, full_cal), kb(img, full_cal)
        report["real_photos"][stem] = {"eye": EYE_READING[stem], "stage_a": [ra.value, ra.confidence],
                                       "stage_b": [rb.value, rb.confidence]}
    print(json.dumps(report, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
