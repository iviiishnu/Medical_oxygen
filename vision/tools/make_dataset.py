"""Build the YOLO-pose dataset from the real panel photos (+ procedural gauges).

usage: python vision/tools/make_dataset.py --out data/gauge_pose --n 6000

Sources (weights):  every samples/real/<name>.jpg with .calibration.json + .needle.json
(80 %, split evenly), procedural gauges 20 %.
Splits: train 90% / val 10%, plus a separate held-out set "test" rendered from the
real photos with a different seed (never seen in training) for the accuracy report.
"""
from __future__ import annotations

import argparse
import csv
import math
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
TILT_P = 0.5                 # share of training dials seen from the side (camera angle up to 40 deg)
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


class RandomGaugeSource:
    """A brand-new random gauge every call (dialtext_synth: any range / face / font / bezel / needle),
    so the dial finder learns dials in general, not just the two hospital gauges.
    Keypoints are geometric: zero = clockwise-first end of the printed scale, max = the other end."""
    name = "random"
    range = (0.0, 1.0)

    def __init__(self, rng):
        self.rng = rng

    def render(self, v):
        from o2gauge.dialtext_synth import C0, RC, DialRender, _ang_pt
        rd = DialRender(self.rng)
        img = np.ascontiguousarray(np.asarray(rd.img)[:, :, ::-1])
        gt = {"center": [C0, C0], "radius": RC, "tip": list(rd.needle_tip),
              "zero": list(_ang_pt(rd.start, 0.95 * RC)), "max": list(_ang_pt(rd.start + rd.sweep, 0.95 * RC)),
              "lamps": [], "min_value": 0.0, "max_value": 1.0, "value": float(np.clip(rd.value_frac, 0, 1))}
        return img, gt


class SynanthropicSource:
    """Synanthropic 'reading-analog-dial' keypoint set (MIT; 34k rendered dials of many designs on a
    magenta key, file name = start_kp center end_kp tip in 640 px). The magenta is replaced by a
    real background (gauge photos from Roboflow-100 'gauge', the panel photos), so the model learns
    dial faces, needles and start/end marks it has never seen on the two hospital panels."""
    name = "synanthropic"
    range = (0.0, 1.0)

    def __init__(self, folder, bg_folders, rng):
        self.files = sorted(Path(folder).glob("*.jpg"))
        self.bgs = [p for f in bg_folders for p in sorted(Path(f).glob("*.jpg"))]
        self.rng = rng
        if not self.files:
            raise FileNotFoundError(folder)

    def render(self, v):
        rng = self.rng
        for _ in range(10):
            p = self.files[int(rng.integers(len(self.files)))]
            nums = [s for s in p.stem.split("_") if "-" in s][:4]
            if len(nums) == 4:
                break
        start, center, end, tip = (tuple(float(t) for t in s.split("-")) for s in nums)
        img = cv2.imread(str(p))
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        key = cv2.inRange(hsv, (135, 80, 80), (165, 255, 255))           # magenta background
        key = cv2.morphologyEx(key, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        fg = 255 - key
        # scale marks sit just inside the rim (same convention as the random gauges: marks at 0.92-0.95 R)
        radius = max(math.dist(start, center), math.dist(end, center)) / 0.92
        if cv2.countNonZero(key) < 0.05 * key.size:                     # no magenta key: keep the render
            fg[:] = 255
        a = cv2.GaussianBlur(fg, (5, 5), 0).astype(np.float32)[..., None] / 255.0
        # magenta spill on the anti-aliased edge: desaturate it
        bg = cv2.imread(str(self.bgs[int(rng.integers(len(self.bgs)))])) if self.bgs else None
        if bg is None:
            bg = np.full_like(img, int(rng.integers(30, 220)))
        h, w = img.shape[:2]
        bh, bw = bg.shape[:2]
        k = max(w / bw, h / bh) * rng.uniform(1.0, 2.0)
        bg = cv2.resize(bg, (int(bw * k) + 1, int(bh * k) + 1))
        y0, x0 = int(rng.integers(0, bg.shape[0] - h + 1)), int(rng.integers(0, bg.shape[1] - w + 1))
        bg = bg[y0:y0 + h, x0:x0 + w]
        out = (img * a + bg * (1 - a)).astype(np.uint8)
        gt = {"center": list(center), "radius": radius, "tip": list(tip), "zero": list(start), "max": list(end),
              "lamps": [], "min_value": 0.0, "max_value": 1.0, "value": 0.0}
        return out, gt


def tilt(img, gt, rng, max_deg=40.0):
    """Camera looking at the dial from the side: real foreshortening (not random corner jitter)."""
    h, w = img.shape[:2]
    c = np.float32(gt["center"])
    yaw, pitch = np.radians(rng.uniform(-max_deg, max_deg, 2))
    f = 1.6 * max(h, w)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = []
    for x, y in src:
        X, Y = x - c[0], y - c[1]
        # rotate the dial plane (yaw about y, pitch about x), pinhole projection back
        x1, z1 = X * math.cos(yaw), X * math.sin(yaw)
        y2, z2 = Y * math.cos(pitch) - z1 * math.sin(pitch), Y * math.sin(pitch) + z1 * math.cos(pitch)
        z = f + z2
        dst.append([c[0] + f * x1 / z, c[1] + f * y2 / z])
    Hm = cv2.getPerspectiveTransform(src, np.float32(dst))
    img = cv2.warpPerspective(img, Hm, (w, h), borderMode=cv2.BORDER_REPLICATE)
    gt = dict(gt)
    r = gt["radius"]
    rim = np.float32([[[c[0] + r * math.cos(t), c[1] + r * math.sin(t)] for t in np.linspace(0, 2 * math.pi, 16, endpoint=False)]])
    for k in ("center", "tip", "zero", "max"):
        gt[k] = [float(t) for t in cv2.perspectiveTransform(np.float32([[gt[k]]]), Hm)[0, 0]]
    rim = cv2.perspectiveTransform(rim, Hm)[0]
    gt["radius"] = float(np.mean(np.linalg.norm(rim - np.float32(gt["center"]), axis=1)))
    return img, gt


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
        if rng.random() < TILT_P:
            img, gt = tilt(img, gt, rng)
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
    ap.add_argument("--random", type=float, default=0.0, help="fraction of brand-new random (generated) gauges")
    ap.add_argument("--procedural", type=float, default=0.2, help="fraction of procedural (drawn) gauges")
    ap.add_argument("--synanthropic", type=float, default=0.0, help="fraction from the Synanthropic keypoint set")
    ap.add_argument("--syn-dir", default="C:/o2data/keypoint")
    ap.add_argument("--bg-dirs", default="C:/o2data/bg_gauge_rf")
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    rng = np.random.default_rng(a.seed)
    # every real photo that has a .calibration.json and a .needle.json next to it
    stems = sorted(p.with_name(p.name.replace(".needle.json", ""))
                   for p in (ROOT / "samples" / "real").glob("*.needle.json"))
    photos = [PhotoSource(s) for s in stems if Path(f"{s}.calibration.json").exists() and Path(f"{s}.jpg").exists()]
    if not photos:
        sys.exit("no real photos found in samples/real (need name.jpg + .calibration.json + .needle.json)")
    print("real photo sources:", [p.name for p in photos])
    procs = [ProceduralSource(g, rng) for g in GAUGES for _ in range(4)]
    randoms = RandomGaugeSource(np.random.default_rng(a.seed + 7))
    syn = SynanthropicSource(a.syn_dir, a.bg_dirs.split(","), np.random.default_rng(a.seed + 11)) \
        if a.synanthropic > 0 else None
    rows = []
    for split, n in (("train", int(a.n * 0.9)), ("val", a.n - int(a.n * 0.9)), ("test", a.n_test)):
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        r = np.random.default_rng(a.seed + {"train": 0, "val": 1, "test": 99}[split])
        for i in range(n):
            if split == "test":
                src = photos[i % len(photos)]
            else:      # real-photo dials (split evenly), procedural, brand-new random gauges (--random)
                u = r.random()
                src = (photos[int(r.integers(len(photos)))] if u < 1 - a.procedural - a.random - a.synanthropic
                       else procs[int(r.integers(len(procs)))] if u < 1 - a.random - a.synanthropic
                       else randoms if u < 1 - a.synanthropic
                       else syn)
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
