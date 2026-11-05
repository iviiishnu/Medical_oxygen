"""Stage B - keypoint model reader (YOLO pose, 4 keypoints).

Pipeline (identical on Android - see contract/stage_b_spec.md):
  1. crop: square of side 2*CROP_SCALE*radius around the calibrated centre,
     warped to IMGSZ x IMGSZ (crop_affine), RGB, float32 / 255, NCHW (NHWC for TFLite)
  2. model -> detections; keep the most confident one
  3. keypoints (input pixels) -> image pixels via the inverse crop affine
  4. value from the angle between them (geometry.value_from_keypoints)
  5. confidence = det_conf * min(kpt_conf[centre], kpt_conf[tip]),
     penalised if the predicted centre is far from the calibrated centre
Backends: .pt (Ultralytics), .onnx (onnxruntime), .tflite (LiteRT / tflite-runtime / TF).
"""
from __future__ import annotations

import math
import time
from pathlib import Path

import cv2
import numpy as np

from .calibration import Calibration, apply_affine
from .dataset import CROP_SCALE, IMGSZ, crop_affine, make_crop
from .geometry import value_from_keypoints, dial_angle
from .stage_a import DEAD_ZONE_MAX_CONF, NeedleResult

MAX_CENTER_OFFSET = 0.15     # x radius: further than this from the tapped centre is suspicious


def decode(out: np.ndarray, n_kpt: int = 4) -> tuple[float, np.ndarray] | None:
    """Raw model output -> (det_conf, kpts[n_kpt, 3] in input pixels) of the best detection.

    Handles both YOLO layouts:
      end-to-end (YOLO26 default): (1, max_det, 6 + 3k) = x1 y1 x2 y2 conf cls kpts...
      classic (YOLO11 / v8):       (1, 5 + 3k, anchors) = cx cy w h conf kpts...
    """
    o = np.asarray(out)
    if o.ndim == 3:
        o = o[0]
    width = 6 + 3 * n_kpt
    if o.shape[-1] == width and o.shape[0] != 5 + 3 * n_kpt:          # end-to-end rows
        i = int(np.argmax(o[:, 4]))
        return float(o[i, 4]), o[i, 6:].reshape(n_kpt, 3).astype(np.float64)
    if o.shape[0] == 5 + 3 * n_kpt:                                   # classic, channels first
        o = o.T
    if o.shape[-1] == 5 + 3 * n_kpt:
        i = int(np.argmax(o[:, 4]))
        return float(o[i, 4]), o[i, 5:].reshape(n_kpt, 3).astype(np.float64)
    raise ValueError(f"unexpected model output shape {np.asarray(out).shape}")


class KeypointReader:
    def __init__(self, model_path: str | Path, use_cal_marks: bool = True):
        self.path = Path(model_path)
        self.use_cal_marks = use_cal_marks
        self.backend = self.path.suffix.lower()
        self.last_ms = 0.0
        if self.backend == ".pt":
            from ultralytics import YOLO
            self.model = YOLO(str(self.path))
        elif self.backend == ".onnx":
            import onnxruntime as ort
            self.sess = ort.InferenceSession(str(self.path), providers=["CPUExecutionProvider"])
            self.inp = self.sess.get_inputs()[0].name
        elif self.backend == ".tflite":
            self.interp = _load_tflite(self.path)
            self.interp.allocate_tensors()
            self.in_det = self.interp.get_input_details()[0]
            self.out_det = self.interp.get_output_details()[0]
        else:
            raise ValueError(f"unsupported model {self.path}")

    # ------------------------------------------------------------------
    def infer(self, crop_bgr: np.ndarray):
        """crop (IMGSZ x IMGSZ BGR) -> (det_conf, kpts in input px) or None."""
        t0 = time.perf_counter()
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        if self.backend == ".pt":
            r = self.model.predict(crop_bgr, imgsz=IMGSZ, verbose=False, conf=0.01)[0]
            if r.keypoints is None or len(r.boxes) == 0:
                res = None
            else:
                i = int(r.boxes.conf.argmax())
                k = r.keypoints.data[i].cpu().numpy().astype(np.float64)
                res = (float(r.boxes.conf[i]), k)
        elif self.backend == ".onnx":
            x = np.transpose(rgb, (2, 0, 1))[None]
            res = decode(self.sess.run(None, {self.inp: x})[0])
        else:
            x = rgb[None]
            if self.in_det["dtype"] == np.uint8 or self.in_det["dtype"] == np.int8:
                s, z = self.in_det["quantization"]
                x = np.clip(np.round(x / s + z), np.iinfo(self.in_det["dtype"]).min,
                            np.iinfo(self.in_det["dtype"]).max).astype(self.in_det["dtype"])
            self.interp.set_tensor(self.in_det["index"], x)
            self.interp.invoke()
            y = self.interp.get_tensor(self.out_det["index"]).astype(np.float32)
            if self.out_det["dtype"] in (np.uint8, np.int8):
                s, z = self.out_det["quantization"]
                y = (y - z) * s
            res = decode(y)
            if res is not None and res[1][:, :2].max() <= 1.5:      # TFLite exports normalised coords
                res = (res[0], res[1] * [IMGSZ, IMGSZ, 1])
        self.last_ms = (time.perf_counter() - t0) * 1000
        return res

    def __call__(self, img: np.ndarray, cal: Calibration) -> NeedleResult:
        cx, cy = cal.center
        M = crop_affine(cx, cy, cal.radius, CROP_SCALE)
        crop = make_crop(img, M)
        res = self.infer(crop)
        if res is None:
            return NeedleResult(None, None, 0.0, False, method="stage_b", reason="no_detection")
        det_conf, k = res
        Minv = cv2.invertAffineTransform(M)
        pts = k[:, :2] @ Minv[:, :2].T + Minv[:, 2]
        center, tip, zero, maxp = pts
        if self.use_cal_marks:
            zero, maxp = cal.zero_point, cal.max_point
        # off-axis camera: measure angles in the perspective-corrected frame, like Stage A
        rect = cal.rectification()
        if rect is not None:
            Mr = rect[0]
            center, tip, zero, maxp = (apply_affine(Mr, p) for p in (center, tip, zero, maxp))
        value, in_range = value_from_keypoints(center, tip, zero, maxp, cal.min_value, cal.max_value, cal.direction)
        conf = det_conf * float(min(k[0, 2], k[1, 2]))
        off = math.dist(pts[0], cal.center) / cal.radius
        if off > MAX_CENTER_OFFSET:
            conf *= max(0.0, 1 - (off - MAX_CENTER_OFFSET) / MAX_CENTER_OFFSET)
        if not in_range:
            conf = min(conf, DEAD_ZONE_MAX_CONF)
        angle = dial_angle(center[0], center[1], tip[0], tip[1])
        return NeedleResult(round(float(value), 3), round(angle, 2), round(float(conf), 3), in_range,
                            method="stage_b", debug={"kpts_img": pts.tolist(), "kpt_conf": k[:, 2].tolist(),
                                                     "det_conf": det_conf, "ms": self.last_ms})


def _load_tflite(path: Path):
    for mod, attr in (("ai_edge_litert.interpreter", "Interpreter"), ("tflite_runtime.interpreter", "Interpreter"),
                      ("tensorflow.lite", "Interpreter")):
        try:
            m = __import__(mod, fromlist=[attr])
            return getattr(m, attr)(model_path=str(path))
        except ImportError:
            continue
    raise ImportError("install ai-edge-litert (pip install ai-edge-litert) to run .tflite models in Python")
