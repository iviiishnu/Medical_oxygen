"""Build the YOLO-pose dataset from the real panel photos (+ procedural gauges).

usage: python vision/tools/make_dataset.py --out data/gauge_pose --n 6000

Sources (weights):  real alarm_box photo 40%, real Magnate photo 40%, procedural 20%.
Splits: train 90% / val 10%, plus a separate held-out set "test" rendered from the
real photos with a different seed (never seen in training) for the accuracy report.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from o2gauge.dataset import IMGSZ, crop_affine, make_crop, warp_points, yolo_pose_label  # noqa: E402
from o2gauge.photo_synth import load_photo_dial                                            # noqa: E402
from o2gauge.synth import GAUGES, AugParams, Layout, augment, render_dial, render_scene     # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GEOM_ONLY = dict(glare_p=0, blur_p=0, noise_p=0, jpeg_p=0, brightness=0, contrast=0, color_shift=0)


class ProceduralSource:
    """Procedural gauge with a random layout/dial per instance (variety, not realism)."""
    def __init__(self, spec_name, rng):
        self.spec = GAUGES[spec_name]
        r = float(rng.uniform(110, 190))
        self.lay = Layout(cx=float(rng.uniform(r + 20, 640 - r - 140)) if 640 - r - 140 > r + 20 else 260,
                          cy=float(rng.uniform(r + 10, 480 - r - 10)) if 480 - 2 * r - 20 > 0 else 240, radius=r)
        self.dial = render_dial(self.spec, self.lay, rng)
        self.name = spec_name

    def render(self, v):
        return render_scene(self.spec, v, self.lay, dial_cache=self.dial)

    @property
    def range(self):
        return self.spec.min_value, self.spec.max_value


class PhotoSource:
    def __init__(self, stem):
        self.d = load_photo_dial(stem)
        self.name = self.d.name

    def render(self, v):
        return self.d.render(v)

    @property
    def range(self):
        return self.d.cal.min_value, self.d.cal.max_value


def sample(src, rng, train_aug=True):
    lo, hi = src.range
    v = float(rng.uniform(lo, hi)) if rng.random() > 0.05 else float(rng.choice([lo, hi]))
    img, gt = src.render(v)
    if train_aug:
        img, gt = augment(img, gt, rng, AugParams(persp=0.015, rot_deg=0, **GEOM_ONLY))
        scale = rng.uniform(1.2, 1.7)
        rot = rng.uniform(-8, 8)
        dx, dy = rng.uniform(-0.06, 0.06, 2)
        tap = rng.normal(0, 0.02 * gt["radius"], 2)          # imperfect calibration tap
    else:
        scale, rot, dx, dy, tap = 1.4, 0.0, 0.0, 0.0, np.zeros(2)
    cx, cy = np.asarray(gt["center"]) + tap
    M = crop_affine(cx, cy, gt["radius"], scale, rot, dx, dy)
    crop = make_crop(img, M)
    kpts = warp_points(M, [gt["center"], gt["tip"], gt["zero"], gt["max"]])
    if train_aug:
        dummy = {"lamps": [], "center": [0, 0], "tip": [0, 0], "zero": [0, 0], "max": [0, 0], "radius": 1}
        crop, _ = augment(crop, dummy, rng, AugParams(glare_p=0.5, blur_p=0.4, noise_p=0.5, jpeg_p=0.6,
                                                     brightness=0.3, contrast=0.3, color_shift=0.1))
    radius_px = gt["radius"] * IMGSZ / (2 * scale * gt["radius"])
    return crop, kpts, radius_px, v, gt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "gauge_pose"))
    ap.add_argument("--n", type=int, default=6000)
    ap.add_argument("--n-test", type=int, default=400)
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    rng = np.random.default_rng(a.seed)
    photos = [PhotoSource(ROOT / "samples" / "real" / s) for s in ("alarm_box", "magnate")]
    procs = [ProceduralSource(g, rng) for g in GAUGES for _ in range(4)]
    rows = []
    for split, n in (("train", int(a.n * 0.9)), ("val", a.n - int(a.n * 0.9)), ("test", a.n_test)):
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        r = np.random.default_rng(a.seed + {"train": 0, "val": 1, "test": 99}[split])
        for i in range(n):
            if split == "test":
                src = photos[i % 2]
            else:
                u = r.random()
                src = photos[0] if u < 0.4 else photos[1] if u < 0.8 else procs[int(r.integers(len(procs)))]
            crop, kpts, rpx, v, gt = sample(src, r, train_aug=True)
            name = f"{split}_{i:05d}_{src.name}"
            cv2.imwrite(str(out / "images" / split / f"{name}.jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
            (out / "labels" / split / f"{name}.txt").write_text(yolo_pose_label(kpts, rpx) + "\n")
            rows.append([split, name, src.name, round(v, 4), gt["min_value"], gt["max_value"]])
        print(split, n)
    with open(out / "values.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["split", "name", "source", "value", "min_value", "max_value"])
        w.writerows(rows)
    (out / "data.yaml").write_text(
        f"path: {out.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        "kpt_shape: [4, 3]\nflip_idx: [0, 1, 2, 3]\nnames:\n  0: gauge\n"
        "kpt_names:\n  0: [center, tip, zero, max]\n")
    print("dataset at", out)


if __name__ == "__main__":
    main()
