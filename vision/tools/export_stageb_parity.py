"""Stage B parity fixtures for the Kotlin port (no device needed).

For a few frames it saves:
  contract/parity/stageb/<case>_crop.png   the exact 320x320 model input (uint8, RGB order saved as PNG)
  contract/parity/stageb/<case>_out.bin    raw TFLite output, float32 little-endian, shape [17, 2100]
  contract/parity/stageb/expected.json     calibration, Python Stage B value / confidence / keypoints
Kotlin tests check: fillInput() == crop (+-2/255), decode(out) + value maths == Python (+-0.01).

Run with the export env (needs LiteRT):
  .tools\\export-venv\\Scripts\\python.exe vision/tools/export_stageb_parity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from o2gauge.calibration import Calibration                  # noqa: E402
from o2gauge.dataset import CROP_SCALE, crop_affine, make_crop  # noqa: E402
from o2gauge.stage_b import KeypointReader                     # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main():
    model = ROOT / "vision" / "models" / "gauge_pose_fp32.tflite"
    kb = KeypointReader(model)
    par = json.loads((ROOT / "contract" / "parity" / "expected.json").read_text())
    pick = [c for c in par if c["file"].startswith("real_")] + \
           [c for c in par if c["file"].endswith(("_03.png", "_08.png", "_perspective.png"))]
    out = ROOT / "contract" / "parity" / "stageb"
    out.mkdir(parents=True, exist_ok=True)
    cases = []
    for c in pick:
        img = cv2.imread(str(ROOT / "contract" / "parity" / c["file"]))
        cal = Calibration.from_dict(c["calibration"])
        crop = make_crop(img, crop_affine(cal.center[0], cal.center[1], cal.radius, CROP_SCALE))
        name = Path(c["file"]).stem
        cv2.imwrite(str(out / f"{name}_crop.png"), crop)
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32)[None] / 255.0
        kb.interp.set_tensor(kb.in_det["index"], rgb)
        kb.interp.invoke()
        raw = kb.interp.get_tensor(kb.out_det["index"])[0].astype("<f4")
        raw.tofile(out / f"{name}_out.bin")
        r = kb(img, cal)
        cases.append({"case": name, "frame": c["file"], "out_shape": list(raw.shape),
                      "calibration": cal.to_dict(), "value": r.value, "confidence": r.confidence,
                      "kpts_img": r.debug.get("kpts_img")})
        print(name, r.value, r.confidence)
    (out / "expected.json").write_text(json.dumps(cases, indent=1))


if __name__ == "__main__":
    main()
