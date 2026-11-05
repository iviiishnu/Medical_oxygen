from pathlib import Path

import cv2
import numpy as np
import pytest

from o2gauge.calibration import Calibration
from o2gauge.stage_b import decode

ROOT = Path(__file__).resolve().parents[2]
ONNX = ROOT / "vision" / "models" / "gauge_pose.onnx"


def test_decode_end_to_end_layout():
    o = np.zeros((1, 300, 18), np.float32)
    o[0, 7, 4] = 0.9
    o[0, 7, 6:] = np.arange(12)
    conf, k = decode(o)
    assert conf == pytest.approx(0.9)
    assert k.shape == (4, 3) and k[1, 0] == 3


def test_decode_classic_layouts():
    o = np.zeros((1, 17, 2100), np.float32)
    o[0, 4, 55] = 0.8
    o[0, 5:, 55] = np.arange(12) + 1
    conf, k = decode(o)
    assert conf == pytest.approx(0.8) and k[0, 0] == 1
    conf2, k2 = decode(np.transpose(o, (0, 2, 1)))            # rows layout
    assert conf2 == conf and np.allclose(k2, k)


def test_decode_rejects_unknown_shape():
    with pytest.raises(ValueError):
        decode(np.zeros((1, 9, 9)))


@pytest.mark.skipif(not ONNX.exists(), reason="trained model not present")
@pytest.mark.parametrize("stem,lo,hi", [("alarm_box", 4.6, 5.3), ("magnate", 4.3, 4.6)])
def test_model_reads_real_photos(stem, lo, hi):
    from o2gauge.stage_b import KeypointReader
    kb = KeypointReader(ONNX)
    cal = Calibration.load(ROOT / "samples" / "real" / f"{stem}.calibration.json")
    img = cv2.imread(str(ROOT / "samples" / "real" / f"{stem}.jpg"))
    r = kb(img, cal)
    assert lo <= r.value <= hi and r.confidence > 0.8


@pytest.mark.skipif(not ONNX.exists(), reason="trained model not present")
def test_model_low_confidence_on_blank_frame():
    from o2gauge.stage_b import KeypointReader
    kb = KeypointReader(ONNX)
    cal = Calibration.load(ROOT / "samples" / "real" / "magnate.calibration.json")
    r = kb(np.full((1200, 1600, 3), 128, np.uint8), cal)
    assert r.value is None or r.confidence < 0.5
