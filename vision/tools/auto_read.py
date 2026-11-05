"""Read a gauge photo with NO calibration: finds the dial(s) and lit lamps automatically.

usage: python vision/tools/auto_read.py IMAGE_OR_DIR [--max 16] [--out out/auto] [--json]

Prints NORMAL / ABNORMAL / CAN'T TELL with a confidence %, the needle reading and the lamp
colours, and writes an annotated image to --out.
The gauge type (and so its scale) is recognised automatically from samples/real/. Only pass
--max (the number printed at the END of the scale) to override that, e.g. for a new gauge type.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from o2gauge.auto import AutoReader, draw                 # noqa: E402
from o2gauge.stage_b import KeypointReader                 # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def to_json(name, r):
    v, m = r["verdict"], r["main"]
    return {
        "file": name,
        "verdict": v.verdict,
        "confidence_pct": round(v.confidence * 100),
        "reading": None if m is None or m.value is None else round(m.value, 2),
        "reading_confidence": None if m is None else m.confidence,
        "stage_a_classical": None if m is None else m.stage_a,
        "stage_b_model": None if m is None else m.stage_b,
        "gauge_type": None if m is None else m.gauge_type,
        "scale": None if m is None else m.scale,
        "dials_found": len(r["readings"]),
        "lamps": [{"color": l.color, "box": list(l.box), "strength": l.strength} for l in r["lamps"]],
        "reasons": v.reasons,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--max", type=float, default=None, help="override the recognised scale end value")
    ap.add_argument("--model", default=str(ROOT / "vision/models/gauge_pose.onnx"))
    ap.add_argument("--out", default=str(ROOT / "out/auto"))
    ap.add_argument("--json", action="store_true", help="print JSON only")
    a = ap.parse_args()
    reader = AutoReader(KeypointReader(a.model))
    p = Path(a.path)
    files = sorted(f for f in p.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png")) if p.is_dir() else [p]
    Path(a.out).mkdir(parents=True, exist_ok=True)
    for f in files:
        img = cv2.imread(str(f))
        if img is None:
            print(f"{f.name}: cannot read", file=sys.stderr)
            continue
        r = reader.read(img, a.max)
        j = to_json(f.name, r)
        cv2.imwrite(str(Path(a.out) / f"{f.stem}_auto.jpg"), draw(img, r))
        if a.json:
            print(json.dumps(j))
            continue
        print(f"\n{f.name}:  {j['verdict']}  (confidence {j['confidence_pct']}%)")
        print(f"  reading      : {j['reading']} kg/cm2   [classical {j['stage_a_classical']}, model {j['stage_b_model']}]")
        print(f"  gauge / scale: {j['scale']}")
        print(f"  dials found  : {j['dials_found']}")
        print(f"  lit lamps    : {', '.join(l['color'] for l in j['lamps']) or 'none'}")
        for s in j["reasons"]:
            print(f"   - {s}")
    print(f"\nannotated images -> {a.out}")


if __name__ == "__main__":
    main()
