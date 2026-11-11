"""Train the Stage B keypoint model (YOLO pose, nano) on data/gauge_pose.

usage: python vision/tools/train_pose.py [--epochs 60] [--model yolo26n-pose.pt] [--device cpu]

Augmentations are mostly baked into the dataset (glare, blur, noise, JPEG,
perspective, crop jitter), so the Ultralytics ones are kept gentle:
  * fliplr = 0   (a mirrored gauge would run counter-clockwise - zero/max meaning breaks)
  * mosaic = 0   (the model always sees ONE dial crop, never a mosaic)
  * small scale/translate, no extra rotation (already in the data)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "gauge_pose" / "data.yaml"))
    ap.add_argument("--model", default="yolo26n-pose.pt")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--imgsz", type=int, default=320)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--name", default="gauge_pose")
    ap.add_argument("--pause", type=float, default=0.0, help="seconds to rest after every batch (GPU care)")
    ap.add_argument("--vram", type=float, default=0.0, help="cap the VRAM share (0 = no cap)")
    ap.add_argument("--lr0", type=float, default=0.01)
    a = ap.parse_args()

    import os
    import time
    os.environ.setdefault("MIOPEN_FIND_MODE", "FAST")
    from ultralytics import YOLO
    if a.vram:
        import torch
        if torch.cuda.is_available():
            torch.cuda.set_per_process_memory_fraction(a.vram)
    try:
        model = YOLO(a.model)
    except Exception as e:                                    # older ultralytics: fall back to YOLO11
        print(f"{a.model} unavailable ({e}); using yolo11n-pose.pt")
        model = YOLO("yolo11n-pose.pt")
    if a.pause:
        model.add_callback("on_train_batch_end", lambda _t: time.sleep(a.pause))
    model.train(
        data=a.data, epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, device=a.device, workers=a.workers,
        project=str(ROOT / "runs"), name=a.name, exist_ok=True,
        fliplr=0.0, flipud=0.0, mosaic=0.0, mixup=0.0, degrees=0.0, scale=0.1, translate=0.05,
        hsv_h=0.01, hsv_s=0.3, hsv_v=0.3, close_mosaic=0,
        cos_lr=True, patience=20, pose=16.0, plots=True, seed=0, deterministic=False, lr0=a.lr0,
    )
    best = ROOT / "runs" / a.name / "weights" / "best.pt"
    dst = ROOT / "vision" / "models" / "gauge_pose.pt"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(best, dst)
    print("best weights ->", dst)


if __name__ == "__main__":
    sys.exit(main())
