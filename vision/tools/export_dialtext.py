"""Export the dial-text models to ONNX (run in the export venv, CPU torch + onnx).

    .tools\\export-venv\\Scripts\\python.exe vision/tools/export_dialtext.py
-> vision/models/dialtext_det.onnx, dialtext_rec.onnx (+ an onnxruntime == torch check)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vision"))
from o2gauge.dialtext_geom import REC_H, REC_W           # noqa: E402
from o2gauge.dialtext_models import TextDet, TextRec     # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "vision/models"))
    ap.add_argument("--dst", default=str(ROOT / "vision/models"))
    a = ap.parse_args()
    src, dst = Path(a.src), Path(a.dst)
    det, rec = TextDet().eval(), TextRec().eval()
    det.load_state_dict(torch.load(src / "dialtext_det.pt", map_location="cpu"))
    rec.load_state_dict(torch.load(src / "dialtext_rec.pt", map_location="cpu"))
    xd = torch.rand(1, 3, 512, 512)
    xr = torch.rand(4, 1, REC_H, REC_W) * 2 - 1
    torch.onnx.export(det, xd, str(dst / "dialtext_det.onnx"), input_names=["image"], output_names=["text_logits"],
                      dynamic_axes={"image": {0: "n", 2: "h", 3: "w"}, "text_logits": {0: "n", 2: "h2", 3: "w2"}},
                      opset_version=17, dynamo=False)
    torch.onnx.export(rec, xr, str(dst / "dialtext_rec.onnx"), input_names=["text"], output_names=["char_logits"],
                      dynamic_axes={"text": {0: "n"}, "char_logits": {0: "n"}}, opset_version=17, dynamo=False)
    import onnxruntime as ort
    for name, m, x in (("dialtext_det", det, torch.rand(1, 3, 192, 512)), ("dialtext_rec", rec, xr)):
        s = ort.InferenceSession(str(dst / f"{name}.onnx"), providers=["CPUExecutionProvider"])
        y = s.run(None, {s.get_inputs()[0].name: x.numpy()})[0]
        with torch.no_grad():
            yt = m(x).numpy()
        print(name, "max |onnx - torch| =", float(np.abs(y - yt).max()), "size", (dst / f"{name}.onnx").stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
