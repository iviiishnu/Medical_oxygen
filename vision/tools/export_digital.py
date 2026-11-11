"""Export the digital-display models to ONNX.

    .tools\\export-venv\\Scripts\\python.exe vision/tools/export_digital.py rec
    .tools\\rocm-venv\\Scripts\\python.exe   vision/tools/export_digital.py det
-> vision/models/digit_rec.onnx, digital_det.onnx (+ an onnxruntime == torch check for rec)
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vision"))
MODELS = ROOT / "vision/models"


def rec():
    import torch
    from o2gauge.dialtext_geom import REC_H, REC_W
    from o2gauge.dialtext_models import TextRec
    from o2gauge.digital import DIG_CHARS
    m = TextRec(n_class=len(DIG_CHARS) + 1).eval()
    m.load_state_dict(torch.load(MODELS / "digit_rec.pt", map_location="cpu"))
    x = torch.rand(2, 1, REC_H, REC_W) * 2 - 1
    torch.onnx.export(m, x, str(MODELS / "digit_rec.onnx"), input_names=["strip"], output_names=["char_logits"],
                      dynamic_axes={"strip": {0: "n"}, "char_logits": {0: "n"}}, opset_version=17, dynamo=False)
    import onnxruntime as ort
    s = ort.InferenceSession(str(MODELS / "digit_rec.onnx"), providers=["CPUExecutionProvider"])
    y = s.run(None, {"strip": x.numpy()})[0]
    with torch.no_grad():
        yt = m(x).numpy()
    print("digit_rec max |onnx - torch| =", float(np.abs(y - yt).max()))


def det():
    from ultralytics import YOLO
    p = YOLO(str(MODELS / "digital_det.pt")).export(format="onnx", imgsz=640, opset=17, simplify=False, dynamic=False)
    shutil.move(p, MODELS / "digital_det.onnx")
    print("->", MODELS / "digital_det.onnx")


if __name__ == "__main__":
    {"rec": rec, "det": det}[sys.argv[1]]()
