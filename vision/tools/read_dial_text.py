"""Show what the dial-text reader sees: every word / number on every dial, the fitted scale(s),
unit and gas name. Writes <image>_text.jpg next to --out.

usage: python vision/tools/read_dial_text.py photo.jpg [--out folder] [--models folder]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vision"))
from o2gauge.auto import find_dials                   # noqa: E402
from o2gauge.dialtext import DialTextReader            # noqa: E402
from o2gauge.stage_b import KeypointReader             # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--out", default=".")
    ap.add_argument("--models", default=str(ROOT / "vision/models"))
    a = ap.parse_args()
    m = Path(a.models)
    tr = DialTextReader(m / "dialtext_det.onnx", m / "dialtext_rec.onnx")
    kp = KeypointReader(ROOT / "vision/models/gauge_pose.onnx")
    for p in a.images:
        img = cv2.imread(p)
        vis = img.copy()
        dials = sorted(find_dials(img, kp, 6), key=lambda d: d.center[0])
        print(f"== {p}: {len(dials)} dial(s)")
        for i, d in enumerate(dials, 1):
            dt = tr.read(img, *d.center, d.radius, d.kpts)
            print(f"  #{i} centre ({d.center[0]:.0f},{d.center[1]:.0f}) r {d.radius:.0f}  gas={dt.gas} "
                  f"({dt.gas_text!r}) units={dt.units}")
            for b in sorted(dt.boxes, key=lambda b: (b.where, b.angle)):
                tag = f"num {b.num:g}" if b.num is not None else "word"
                print(f"     {b.where:12s} ang {b.angle:5.0f} rho {b.rho:4.2f} h {b.h:4.1f}  {b.text!r:24s} "
                      f"{tag} conf {b.conf:.2f}")
                col = (0, 160, 0) if b.num is not None else (200, 90, 0)
                cv2.circle(vis, (int(b.x), int(b.y)), max(3, int(b.h / 2)), col, 2)
                cv2.putText(vis, b.text, (int(b.x), int(b.y - b.h)), cv2.FONT_HERSHEY_SIMPLEX,
                            max(0.4, b.h / 30), col, 1, cv2.LINE_AA)
            for k, f in enumerate(dt.scales):
                print(f"     scale {k + 1}: {f.describe()}  step {f.step:g}  labels {[l.text for l in f.labels]} "
                      f"resid {f.resid:.1f} deg conf {f.confidence:.2f} {'(unit inferred)' if f.unit_inferred else ''}")
            cv2.circle(vis, (int(d.center[0]), int(d.center[1])), int(d.radius), (0, 220, 220), 2)
        out = Path(a.out) / (Path(p).stem + "_text.jpg")
        cv2.imwrite(str(out), vis)
        print("  ->", out)


if __name__ == "__main__":
    main()
