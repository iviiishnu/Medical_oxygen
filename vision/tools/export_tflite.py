"""Export the trained keypoint model to ONNX + TFLite (fp32/fp16 and int8).

Run with the Python 3.12 export environment (TensorFlow has no 3.14 build):
  .tools\\export-venv\\Scripts\\python.exe vision/tools/export_tflite.py

Outputs in vision/models/:
  gauge_pose.onnx, gauge_pose_float16.tflite, gauge_pose_int8.tflite
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "vision" / "models"


def main():
    from ultralytics import YOLO
    pt = MODELS / "gauge_pose.pt"
    data = ROOT / "data" / "gauge_pose" / "data.yaml"

    onnx = YOLO(str(pt)).export(format="onnx", imgsz=320, simplify=True, opset=17, dynamic=False)
    shutil.copy(onnx, MODELS / "gauge_pose.onnx")

    out = YOLO(str(pt)).export(format="tflite", imgsz=320, half=True)          # -> *_saved_model/
    sm = Path(out).parent
    for f in sm.glob("*.tflite"):
        print("tflite:", f.name, f.stat().st_size // 1024, "KB")
    for name in ("gauge_pose_float16.tflite", "gauge_pose_float32.tflite"):
        if (sm / name).exists():
            shutil.copy(sm / name, MODELS / name)

    out8 = YOLO(str(pt)).export(format="tflite", imgsz=320, int8=True, data=str(data), fraction=0.1)
    sm8 = Path(out8).parent
    for f in sm8.glob("*.tflite"):
        print("tflite:", f.name, f.stat().st_size // 1024, "KB")
    for name in ("gauge_pose_int8.tflite", "gauge_pose_full_integer_quant.tflite"):
        if (sm8 / name).exists():
            shutil.copy(sm8 / name, MODELS / name)
    print("models:", sorted(p.name for p in MODELS.iterdir()))


if __name__ == "__main__":
    sys.exit(main())
