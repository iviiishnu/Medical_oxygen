"""Accuracy sweep of Stage A + lamp reader on synthetic frames.

usage: python vision/tools/eval_stage_a.py [--n 200] [--aug] [--gauge alarm_box_16]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from o2gauge.calibration import Calibration          # noqa: E402
from o2gauge.lamps import read_lamps                  # noqa: E402
from o2gauge.stage_a import read_needle               # noqa: E402
from o2gauge.synth import GAUGES, Layout, AugParams, augment, render_dial, render_scene, calibration_from_gt  # noqa: E402


def run(gauge: str, n: int, aug: bool, seed: int = 1, persp: float = 0.0, glare_p: float = 0.6):
    spec = GAUGES[gauge]
    lay = Layout()
    rng = np.random.default_rng(seed)
    dial = render_dial(spec, lay, rng)
    _, gt0 = render_scene(spec, spec.min_value, lay, dial_cache=dial)
    cal = Calibration.from_dict(calibration_from_gt(gt0))
    errs, confs, lamp_ok, times = [], [], 0, []
    worst = (0, None)
    unread = 0
    for _ in range(n):
        v = float(rng.uniform(spec.min_value, spec.max_value))
        img, gt = render_scene(spec, v, lay, dial_cache=dial)
        if aug:
            img, gt = augment(img, gt, rng, AugParams(persp=persp, glare_p=glare_p))
        t0 = time.perf_counter()
        r = read_needle(img, cal)
        ls, _ = read_lamps(img, cal)
        times.append((time.perf_counter() - t0) * 1000)
        lamp_ok += ls == gt["lamp_state"]
        if r.value is None:
            unread += 1
            continue
        e = abs(r.value - v)
        errs.append(e)
        confs.append(r.confidence)
        if e > worst[0]:
            worst = (e, (round(v, 2), r.value, r.confidence))
    errs = np.array(errs)
    return {
        "gauge": gauge, "n": n, "aug": aug,
        "mean_err": round(float(errs.mean()), 4), "p95_err": round(float(np.percentile(errs, 95)), 4),
        "worst_err": round(float(errs.max()), 4), "worst_case(true,read,conf)": worst[1],
        "within_0.2": round(float((errs <= 0.2).mean()), 4),
        "lamp_acc": round(lamp_ok / n, 4), "unreadable": unread,
        "mean_conf": round(float(np.mean(confs)), 3),
        "ms_per_frame": round(float(np.median(times)), 2),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--aug", action="store_true")
    ap.add_argument("--gauge", default="all")
    ap.add_argument("--persp", type=float, default=0.0)
    a = ap.parse_args()
    for g in (GAUGES if a.gauge == "all" else [a.gauge]):
        print(run(g, a.n, a.aug, persp=a.persp))
