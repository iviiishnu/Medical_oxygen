"""Read one image (or a folder) and print the JSON reading message.

usage: python vision/tools/read_gauge.py IMAGE_OR_DIR CALIBRATION.json [--debug-dir out/] [--model best.pt]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from o2gauge.calibration import Calibration      # noqa: E402
from o2gauge.config import MonitorConfig         # noqa: E402
from o2gauge.pipeline import GaugePipeline       # noqa: E402
from o2gauge.stage_a import draw_debug           # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("calibration")
    ap.add_argument("--config", default=None)
    ap.add_argument("--debug-dir", default=None)
    ap.add_argument("--model", default=None, help="Stage B weights (.pt/.onnx/.tflite)")
    a = ap.parse_args()
    cal = Calibration.load(a.calibration)
    cfg = MonitorConfig.load(a.config) if a.config else MonitorConfig.load()
    stage_b = None
    if a.model:
        from o2gauge.stage_b import KeypointReader
        stage_b = KeypointReader(a.model)
    pipe = GaugePipeline(cal, cfg, stage_b)
    p = Path(a.path)
    files = sorted(f for f in p.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png")) if p.is_dir() else [p]
    for f in files:
        img = cv2.imread(str(f))
        if img is None:
            print(f"{f.name}: cannot read", file=sys.stderr)
            continue
        msg, dbg = pipe.read(img)
        print(json.dumps({"file": f.name, **msg}))
        if a.debug_dir:
            Path(a.debug_dir).mkdir(parents=True, exist_ok=True)
            lit = {k: v["lit"] for k, v in dbg["lamps"].items()}
            cv2.imwrite(str(Path(a.debug_dir) / f"{f.stem}_debug.jpg"), draw_debug(img, cal, dbg["stage_a"], lit))


if __name__ == "__main__":
    main()
