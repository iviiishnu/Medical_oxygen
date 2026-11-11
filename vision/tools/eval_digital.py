"""Test the digital-display reader.

  1. held-out synthetic scenes (new seed, real backgrounds, any camera angle): detection recall,
     exact string, value correct
  2. REAL photos: blood-pressure monitor LCD (HF chakibmed/bp-monitor-seven-segment, test split):
     each photo shows systolic / diastolic / pulse - how many of the 3 numbers are read exactly
  3. false alarms: photos WITHOUT a digital display (the hospital panels, real analog gauge photos)

usage: python vision/tools/eval_digital.py [--n 300] [--sheet out/digital_eval]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vision"))
from o2gauge.digital import DigitalReader             # noqa: E402
from o2gauge.digital_synth import scene                # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--bp", default="C:/o2data/bp_lcd/readings/test")
    ap.add_argument("--sheet", default=str(ROOT / "out/digital_eval"))
    ap.add_argument("--out", default=str(ROOT / "docs/eval_digital.json"))
    a = ap.parse_args()
    Path(a.sheet).mkdir(parents=True, exist_ok=True)
    dr = DigitalReader()
    res = {}

    # 1 ---- synthetic held-out
    bgs = sorted(Path("C:/o2data/bg_gauge_rf").glob("*.jpg"))[::3] + sorted((ROOT / "samples/real").glob("*.jpg"))
    rng = np.random.default_rng(424242)
    found = exact = close = 0
    t0 = time.perf_counter()
    for i in range(a.n):
        bg = cv2.imread(str(bgs[int(rng.integers(len(bgs)))]))
        img, q, label = scene(rng, bg, max_side=int(rng.integers(640, 1280)))
        rs = dr.read(img)
        x0, y0 = q.min(0)
        x1, y1 = q.max(0)
        hit = [r for r in rs if r.box[0] < x1 and r.box[2] > x0 and r.box[1] < y1 and r.box[3] > y0]
        if hit:
            found += 1
            r = hit[0]
            exact += r.text == label
            try:
                close += r.value is not None and abs(r.value - float(label)) < 1e-6
            except ValueError:
                close += r.text == label
            if r.text != label and i < 400:
                cv2.rectangle(img, r.box[:2], r.box[2:], (0, 255, 255), 2)
                cv2.imwrite(str(Path(a.sheet) / f"syn_{i:03d}_true_{label}_read_{r.text or 'none'}.jpg"), img)
        elif i < 400:
            cv2.imwrite(str(Path(a.sheet) / f"syn_{i:03d}_true_{label}_MISSED.jpg"), img)
    ms = (time.perf_counter() - t0) / a.n * 1000
    res["synthetic"] = {"n": a.n, "found": round(found / a.n, 3), "exact_string": round(exact / a.n, 3),
                        "value_correct": round(close / a.n, 3), "ms_per_image": round(ms)}
    print("synthetic", res["synthetic"], flush=True)

    # 2 ---- real LCD photos
    rows = list(csv.DictReader(open(Path(a.bp) / "metadata.csv")))
    got = tot = 0
    per = []
    for r in rows:
        img = cv2.imread(str(Path(a.bp) / r["file_name"]))
        if img is None:
            continue
        # these are tight display crops (~150 px): give the reader a bit of surround like a real photo
        img = cv2.copyMakeBorder(cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC),
                                 120, 120, 160, 160, cv2.BORDER_CONSTANT, value=(60, 60, 60))
        reads = dr.read(img, max_displays=6)
        vals = {x.text for x in reads}
        want = [r["systolic"], r["diastolic"], r["pulse"]]
        ok = [w for w in want if w in vals]
        got += len(ok)
        tot += 3
        per.append({"file": r["file_name"], "want": want, "read": sorted(vals)})
        if len(ok) < 3:
            for x in reads:
                cv2.rectangle(img, x.box[:2], x.box[2:], (255, 0, 255), 2)
                cv2.putText(img, x.text, (x.box[0], x.box[1] - 4), 0, 0.8, (255, 0, 255), 2)
            cv2.imwrite(str(Path(a.sheet) / f"bp_{r['file_name']}"), img)
    res["real_bp_lcd"] = {"photos": len(per), "numbers": tot, "read_exact": round(got / max(tot, 1), 3)}
    print("real LCD", res["real_bp_lcd"], flush=True)

    # 3 ---- false alarms on photos with no digital display
    neg = sorted((ROOT / "samples/real").glob("*.jpg")) + sorted(Path("C:/o2data/bg_gauge_rf").glob("test_*.jpg"))
    fa = 0
    for p in neg:
        img = cv2.imread(str(p))
        rs = [r for r in dr.read(img) if r.value is not None and r.confidence >= 0.5]
        if rs:
            fa += 1
            for x in rs:
                cv2.rectangle(img, x.box[:2], x.box[2:], (0, 0, 255), 2)
            cv2.imwrite(str(Path(a.sheet) / f"falsealarm_{p.name}"), img)
    res["no_display_photos"] = {"n": len(neg), "false_display": fa, "rate": round(fa / max(len(neg), 1), 3)}
    print("false alarms", res["no_display_photos"], flush=True)
    res["bp_details"] = per
    Path(a.out).write_text(json.dumps(res, indent=1))
    print("->", a.out)


if __name__ == "__main__":
    main()
