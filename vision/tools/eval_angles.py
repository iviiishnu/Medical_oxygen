"""Camera-angle test on the REAL panel photos.

The photo is re-projected as if the camera had been turned (yaw / pitch up to +-35 deg) - a real
perspective change of the whole panel, not a flat rotation. A good reader gives the same reading
from every angle; we report how far each reading moves from the straight-on reading.

usage: python vision/tools/eval_angles.py [--model vision/models/gauge_pose.onnx] [--no-rectify]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vision"))
from o2gauge.auto import AutoReader, draw            # noqa: E402
from o2gauge.stage_b import KeypointReader             # noqa: E402

ANGLES = [(0, 0), (20, 0), (-20, 0), (0, 20), (0, -20), (35, 0), (-35, 0), (0, 30), (25, 20), (-25, -20)]


def turn(img, yaw_deg, pitch_deg):
    h, w = img.shape[:2]
    f = 1.2 * max(h, w)
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = []
    for x, y in src:
        X, Y = x - w / 2, y - h / 2
        x1, z1 = X * math.cos(yaw), X * math.sin(yaw)
        y2, z2 = Y * math.cos(pitch) - z1 * math.sin(pitch), Y * math.sin(pitch) + z1 * math.cos(pitch)
        z = f + z2
        dst.append([w / 2 + f * x1 / z, h / 2 + f * y2 / z])
    dst = np.float32(dst)
    dst -= dst.min(0)
    W, H = (dst.max(0) + 1).astype(int)
    P = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, P, (int(W), int(H)), borderMode=cv2.BORDER_CONSTANT, borderValue=(40, 40, 40))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "vision/models/gauge_pose.onnx"))
    ap.add_argument("--no-rectify", action="store_true")
    ap.add_argument("--panel-model", default=None, help="second model to read recognised hospital gauges")
    ap.add_argument("--out", default=str(ROOT / "docs/eval_angles.json"))
    ap.add_argument("--sheet", default=str(ROOT / "out/angles"))
    a = ap.parse_args()
    Path(a.sheet).mkdir(parents=True, exist_ok=True)
    rd = AutoReader(KeypointReader(a.model), rectify=not a.no_rectify, digital=False,
                    panel_model=KeypointReader(a.panel_model) if a.panel_model else None)
    rows = []
    for stem in ("magnate", "alarm_box"):
        img = cv2.imread(str(ROOT / f"samples/real/{stem}.jpg"))
        base = None
        for yaw, pitch in ANGLES:
            im = turn(img, yaw, pitch)
            r = rd.read(im)
            got = {g.gas or f"#{g.number}": (None if g.value is None else round(g.value, 3))
                   for g in sorted(r["readings"], key=lambda g: g.number)}
            if base is None:
                base = got
            dev = {k: (None if got.get(k) is None or v is None else round(abs(got[k] - v) / (760 / 10.55 if k == "VACUUM" else 1), 3))
                   for k, v in base.items()}
            rows.append({"panel": stem, "yaw": yaw, "pitch": pitch, "verdict": r["verdict"].verdict,
                         "readings": got, "dev_kgcm2_equiv": dev})
            print(stem, yaw, pitch, r["verdict"].verdict, got, flush=True)
            cv2.imwrite(str(Path(a.sheet) / f"{stem}_y{yaw}_p{pitch}.jpg"), cv2.resize(draw(im, r), None, fx=0.5, fy=0.5))
    devs = [d for r in rows for d in r["dev_kgcm2_equiv"].values() if d is not None]
    missing = sum(1 for r in rows for d in r["dev_kgcm2_equiv"].values() if d is None)
    summ = {"cases": len(rows), "dial_readings": len(devs) + missing, "missed": missing,
            "mean_dev": round(float(np.mean(devs)), 3), "max_dev": round(float(np.max(devs)), 3),
            "within_0.2": round(float(np.mean(np.array(devs) <= 0.2)), 3),
            "verdict_normal": sum(r["verdict"] == "NORMAL" for r in rows)}
    print(json.dumps(summ))
    Path(a.out).write_text(json.dumps({"summary": summ, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
