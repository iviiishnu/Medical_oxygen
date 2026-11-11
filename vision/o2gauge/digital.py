"""Digital (seven-segment LCD / LED) gauge reader.

    image -> display detector (YOLO nano, ONNX)  -> digit-area boxes
          -> each box: upright strip -> digit recogniser (CTC, ONNX) -> "12.5"
          -> number + confidence (mean per-character probability)

Both networks are trained only on synthetic displays pasted into real photos at random camera
angles (vision/o2gauge/digital_synth.py, vision/tools/train_digital.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

DIG_CHARS = "0123456789.-"
DIG_IDX = {c: i + 1 for i, c in enumerate(DIG_CHARS)}           # 0 = CTC blank
MODELS = Path(__file__).resolve().parents[1] / "models"
DET_SIZE = 640
NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")


def encode_digits(s: str) -> list[int]:
    return [DIG_IDX[c] for c in s if c in DIG_IDX]


@dataclass
class DigitalReading:
    text: str                      # raw recognised string
    value: float | None            # parsed number (None = not a valid number, e.g. "----")
    confidence: float              # 0..1
    box: tuple[int, int, int, int] # x0 y0 x1 y1 image px (digit area)
    det_conf: float


class DigitalReader:
    def __init__(self, det_path=MODELS / "digital_det.onnx", rec_path=MODELS / "digit_rec.onnx", threads: int = 0):
        import onnxruntime as ort
        so = ort.SessionOptions()
        if threads:
            so.intra_op_num_threads = threads
        self.det = ort.InferenceSession(str(det_path), so, providers=["CPUExecutionProvider"])
        self.rec = ort.InferenceSession(str(rec_path), so, providers=["CPUExecutionProvider"])
        self.det_in = self.det.get_inputs()[0].name
        self.rec_in = self.rec.get_inputs()[0].name
        self.rec_w = self.rec.get_inputs()[0].shape[3] if isinstance(self.rec.get_inputs()[0].shape[3], int) else 192

    @staticmethod
    def available(det_path=MODELS / "digital_det.onnx", rec_path=MODELS / "digit_rec.onnx") -> bool:
        return Path(det_path).exists() and Path(rec_path).exists()

    # ------------------------------------------------------------------ detection
    def detect(self, img, conf: float = 0.35) -> list[tuple[float, tuple[float, float, float, float]]]:
        H, W = img.shape[:2]
        s = DET_SIZE / max(H, W)
        nw, nh = int(round(W * s)), int(round(H * s))
        canvas = np.full((DET_SIZE, DET_SIZE, 3), 114, np.uint8)
        px, py = (DET_SIZE - nw) // 2, (DET_SIZE - nh) // 2
        canvas[py:py + nh, px:px + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        x = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32).transpose(2, 0, 1)[None] / 255.0
        o = np.asarray(self.det.run(None, {self.det_in: x})[0], np.float32)[0]
        boxes = []
        if o.shape[0] in (5, 6) and o.shape[1] > 6:                    # classic: (4+nc, anchors)
            o = o.T
            for row in o:
                c = float(row[4])
                if c >= conf:
                    cx, cy, w, h = row[:4]
                    boxes.append((c, (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)))
            boxes = _nms(boxes, 0.5)
        else:                                                          # end-to-end: x1 y1 x2 y2 conf cls
            for row in o:
                c = float(row[4])
                if c >= conf:
                    boxes.append((c, tuple(float(t) for t in row[:4])))
        out = []
        for c, (x0, y0, x1, y1) in boxes:
            out.append((c, ((x0 - px) / s, (y0 - py) / s, (x1 - px) / s, (y1 - py) / s)))
        out.sort(key=lambda t: -t[0])
        return out

    # ------------------------------------------------------------------ recognition
    def recognise(self, img, box) -> tuple[str, float]:
        from .digital_synth import quad_crop, rec_from_strip
        x0, y0, x1, y1 = box
        q = np.float32([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
        best = ("", 0.0)
        for pad in (0.0, 0.08):                                        # tight box and a slightly larger one
            h = y1 - y0
            qq = q + np.float32([[-pad, -pad], [pad, -pad], [pad, pad], [-pad, pad]]) * h
            x = rec_from_strip(quad_crop(img, qq, 48))
            if x is None:
                continue
            lg = self.rec.run(None, {self.rec_in: x[None, None].astype(np.float32)})[0][0]
            p = np.exp(lg - lg.max(-1, keepdims=True))
            p /= p.sum(-1, keepdims=True)
            k = p.argmax(-1)
            chars, probs, prev = [], [], 0
            for t, c in enumerate(k):
                if c != prev and c != 0:
                    chars.append(DIG_CHARS[c - 1])
                    probs.append(float(p[t, c]))
                prev = c
            s = "".join(chars)
            conf = float(np.mean(probs)) if probs else 0.0
            if NUM_RE.match(s):
                conf = conf
            else:
                conf *= 0.6
            if conf > best[1]:
                best = (s, conf)
        return best

    def read(self, img, max_displays: int = 3) -> list[DigitalReading]:
        res = []
        for dc, (x0, y0, x1, y1) in self.detect(img)[:max_displays]:
            H, W = img.shape[:2]
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W - 1, x1), min(H - 1, y1)
            if x1 - x0 < 6 or y1 - y0 < 5:
                continue
            s, c = self.recognise(img, (x0, y0, x1, y1))
            v = float(s) if NUM_RE.match(s) else None
            res.append(DigitalReading(s, v, c * (0.5 + 0.5 * dc), (int(x0), int(y0), int(x1), int(y1)), dc))
        return res


def _nms(boxes, thr):
    boxes = sorted(boxes, key=lambda t: -t[0])
    keep = []
    for c, b in boxes:
        if all(_iou(b, k[1]) < thr for k in keep):
            keep.append((c, b))
    return keep


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0
