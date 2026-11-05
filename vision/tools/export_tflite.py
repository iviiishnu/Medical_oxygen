"""Export the trained keypoint model to ONNX + TFLite (LiteRT), on Windows.

Ultralytics' own LiteRT exporter only runs on Linux/macOS, so we:
  1. export ONNX with end2end=False (raw [1, 17, 2100] head - simplest graph to convert;
     stage_b.decode() / TFLiteKeypointModel.decode() handle this layout)
  2. convert with onnx2tf -> float32 + float16 .tflite (NHWC input [1,320,320,3])

Run with the Python 3.12 export environment:
  .tools\\export-venv\\Scripts\\python.exe vision/tools/export_tflite.py
Outputs: vision/models/gauge_pose.onnx, gauge_pose_fp32.tflite, gauge_pose_fp16.tflite
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "vision" / "models"


def main():
    from ultralytics import YOLO
    pt = MODELS / "gauge_pose.pt"
    onnx = Path(YOLO(str(pt)).export(format="onnx", imgsz=320, simplify=True, opset=17, dynamic=False,
                                     end2end=False))
    dst = MODELS / "gauge_pose.onnx"
    if onnx.resolve() != dst.resolve():
        shutil.copy(onnx, dst)
    out = ROOT / "runs" / "onnx2tf"
    if out.exists():
        shutil.rmtree(out)
    cmd = [sys.executable, "-m", "onnx2tf", "-i", str(dst), "-o", str(out), "-osd", "-coion"]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    for src, name in (("gauge_pose_float32.tflite", "gauge_pose_fp32.tflite"),
                      ("gauge_pose_float16.tflite", "gauge_pose_fp16.tflite")):
        f = out / src
        if f.exists():
            shutil.copy(f, MODELS / name)
            print("tflite:", name, f.stat().st_size // 1024, "KB")
    print("models:", sorted(p.name for p in MODELS.iterdir()))


if __name__ == "__main__":
    sys.exit(main())
