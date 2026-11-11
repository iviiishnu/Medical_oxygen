"""Digital (seven-segment LCD / LED) reader: data + training.

  det-data : synthetic scenes (digital meters pasted into real photos at random camera angles)
             -> YOLO detection dataset, 1 class "display" (the digit area)
  det      : train the display detector (Ultralytics YOLO nano) - gentle on the GPU
  rec      : train the digit-string recogniser (CTC, chars 0-9 . -) on fresh synthetic strips

usage (AMD GPU, ROCm venv):
  python vision/tools/train_digital.py det-data --out C:/o2data/digital_det --n 8000
  .tools\\rocm-venv\\Scripts\\python.exe vision/tools/train_digital.py rec --iters 12000
  .tools\\rocm-venv\\Scripts\\python.exe vision/tools/train_digital.py det --data C:/o2data/digital_det/data.yaml

GPU care ("don't overkill the GPU"): fixed moderate batch, a short pause after every step
(--pause, seconds) so the card is never pinned at 100 %, and a capped VRAM share.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MIOPEN_FIND_MODE", "FAST")
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vision"))
from o2gauge.dialtext_geom import REC_H, REC_W          # noqa: E402
from o2gauge.digital import DIG_CHARS, encode_digits      # noqa: E402
from o2gauge.digital_synth import rec_sample, scene       # noqa: E402

BG_DIRS = ["C:/o2data/bg_gauge_rf", str(ROOT / "samples/real")]


def load_bgs(extra_syn: int = 0, seed: int = 0):
    files = [p for d in BG_DIRS for p in sorted(Path(d).glob("*.jpg"))]
    if extra_syn:
        syn = sorted(Path("C:/o2data/keypoint").glob("*.jpg"))
        if syn:
            r = np.random.default_rng(seed)
            files += [syn[i] for i in r.choice(len(syn), min(extra_syn, len(syn)), replace=False)]
    return files


# ------------------------------------------------------------------------------- detector data
def det_data(a):
    out = Path(a.out)
    files = load_bgs(extra_syn=1500, seed=a.seed)
    print(len(files), "backgrounds", flush=True)
    rng = np.random.default_rng(a.seed)
    for split, n in (("train", int(a.n * 0.9)), ("val", a.n - int(a.n * 0.9))):
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        for i in range(n):
            bg = cv2.imread(str(files[int(rng.integers(len(files)))]))
            if bg is None:
                continue
            lines = []
            if rng.random() < 0.12:                                    # negative: no display at all
                s = 800 / max(bg.shape[:2])
                img = cv2.resize(bg, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            else:
                img, q, _ = scene(rng, bg, max_side=800)
                H, W = img.shape[:2]
                x0, y0 = np.clip(q.min(0), 0, [W - 1, H - 1])
                x1, y1 = np.clip(q.max(0), 0, [W - 1, H - 1])
                if x1 - x0 > 4 and y1 - y0 > 3:
                    lines.append(f"0 {(x0 + x1) / 2 / W:.6f} {(y0 + y1) / 2 / H:.6f} {(x1 - x0) / W:.6f} {(y1 - y0) / H:.6f}")
            name = f"{split}_{i:05d}"
            cv2.imwrite(str(out / "images" / split / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            (out / "labels" / split / f"{name}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
            if i % 500 == 0:
                print(split, i, flush=True)
    (out / "data.yaml").write_text(f"path: {out.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: display\n")
    print("dataset at", out, flush=True)


def det_extra(a):
    """Add close-up and multi-row displays (one LCD window with 1-3 numbers) to an existing dataset."""
    from o2gauge.digital_synth import multi_scene
    out = Path(a.out)
    files = load_bgs(extra_syn=500, seed=a.seed + 1)
    rng = np.random.default_rng(a.seed + 100)
    for split, n in (("train", int(a.n * 0.9)), ("val", a.n - int(a.n * 0.9))):
        for i in range(n):
            bg = cv2.imread(str(files[int(rng.integers(len(files)))]))
            if bg is None:
                continue
            try:
                img, quads, _ = multi_scene(rng, bg, max_side=800, big=rng.random() < 0.5)
            except Exception as e:
                print("gen error", repr(e), flush=True)
                continue
            H, W = img.shape[:2]
            lines = []
            for q in quads:
                x0, y0 = np.clip(q.min(0), 0, [W - 1, H - 1])
                x1, y1 = np.clip(q.max(0), 0, [W - 1, H - 1])
                if x1 - x0 > 4 and y1 - y0 > 3:
                    lines.append(f"0 {(x0 + x1) / 2 / W:.6f} {(y0 + y1) / 2 / H:.6f} {(x1 - x0) / W:.6f} {(y1 - y0) / H:.6f}")
            name = f"x_{split}_{i:05d}"
            cv2.imwrite(str(out / "images" / split / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            (out / "labels" / split / f"{name}.txt").write_text("\n".join(lines) + "\n")
            if i % 500 == 0:
                print("extra", split, i, flush=True)
    print("done", flush=True)


WORDS = ["LOW", "HIGH", "NORMAL", "ALARM", "O2", "OXYGEN", "AIR", "VACUUM", "N2O", "MUTE", "TEST", "POWER", "bar",
         "kg/cm2", "psi", "12", "4.5", "16", "100", "0", "10", "250", "ISO 9001", "CE", "SYSTEM", "PRESSURE", "1.6",
         "WARNING", "FIRE", "EXIT", "Air-4", "MEDICAL GAS", "No. 3", "24 V", "2024", "B-12"]
FONTS = [cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX, cv2.FONT_HERSHEY_COMPLEX, cv2.FONT_HERSHEY_TRIPLEX,
         cv2.FONT_HERSHEY_PLAIN, cv2.FONT_HERSHEY_COMPLEX_SMALL]


def det_neg(a):
    """Hard negatives: printed words / numbers in boxes and on labels (NOT seven-segment) -> no display."""
    out = Path(a.out)
    files = load_bgs(extra_syn=300, seed=a.seed + 2)
    rng = np.random.default_rng(a.seed + 200)
    for split, n in (("train", int(a.n * 0.9)), ("val", a.n - int(a.n * 0.9))):
        for i in range(n):
            bg = cv2.imread(str(files[int(rng.integers(len(files)))]))
            if bg is None:
                continue
            s = 800 / max(bg.shape[:2])
            img = cv2.resize(bg, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            H, W = img.shape[:2]
            for _ in range(int(rng.integers(1, 6))):
                w_ = str(rng.choice(WORDS))
                font = FONTS[int(rng.integers(len(FONTS)))]
                fs = rng.uniform(0.6, 3.0)
                th = max(1, int(fs * rng.uniform(1, 3)))
                (tw, tht), _ = cv2.getTextSize(w_, font, fs, th)
                x = int(rng.uniform(0, max(1, W - tw - 20)))
                y = int(rng.uniform(tht + 10, max(tht + 11, H - 10)))
                col = tuple(float(c) for c in rng.uniform(0, 255, 3))
                if rng.random() < 0.6:                                  # label plate / frame around it
                    pad = int(tht * rng.uniform(0.2, 0.7))
                    plate = tuple(float(c) for c in rng.uniform(0, 255, 3))
                    if rng.random() < 0.5:
                        cv2.rectangle(img, (x - pad, y - tht - pad), (x + tw + pad, y + pad), plate, -1)
                    cv2.rectangle(img, (x - pad, y - tht - pad), (x + tw + pad, y + pad), col, max(1, th // 2))
                cv2.putText(img, w_, (x, y), font, fs, col, th, cv2.LINE_AA)
            from o2gauge.digital_synth import _camera
            img = _camera(img, rng)
            name = f"n_{split}_{i:05d}"
            cv2.imwrite(str(out / "images" / split / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            (out / "labels" / split / f"{name}.txt").write_text("")
    print("done", flush=True)


def det_train(a):
    from ultralytics import YOLO
    import torch
    if torch.cuda.is_available():
        torch.cuda.set_per_process_memory_fraction(a.vram)
    model = YOLO(a.model)

    def breathe(_):
        time.sleep(a.pause)                                           # keep the GPU below 100 %
    model.add_callback("on_train_batch_end", breathe)
    model.train(data=a.data, epochs=a.epochs, imgsz=640, batch=a.batch, device=0 if torch.cuda.is_available() else "cpu",
                workers=a.workers, project=str(ROOT / "runs"), name="digital_det", exist_ok=True,
                fliplr=0.0, mosaic=0.5, degrees=5.0, perspective=0.0005, scale=0.4, translate=0.1,
                hsv_h=0.02, hsv_s=0.5, hsv_v=0.4, close_mosaic=5, cos_lr=True, patience=15, plots=True, seed=0)
    best = ROOT / "runs" / "digital_det" / "weights" / "best.pt"
    import shutil
    shutil.copy(best, ROOT / "vision/models/digital_det.pt")
    print("best ->", ROOT / "vision/models/digital_det.pt", flush=True)


# ------------------------------------------------------------------------------- recogniser
import torch                                                           # noqa: E402
from torch.utils.data import DataLoader, IterableDataset, get_worker_info   # noqa: E402


class RecSynth(IterableDataset):
    def __init__(self, seed, files):
        self.seed, self.files = seed, files

    def __iter__(self):
        wi = get_worker_info()
        rng = np.random.default_rng([self.seed, wi.id if wi else 0, int(time.time() * 1e3) % 100000])
        bgs = [cv2.imread(f) for f in self.files]
        bgs = [b for b in bgs if b is not None]
        while True:
            try:
                x, lab = rec_sample(rng, bgs[int(rng.integers(len(bgs)))])
            except Exception as e:                                     # degenerate random draw: skip
                print("gen error:", repr(e), flush=True)
                continue
            if x is None:
                continue
            yield x, lab


def collate(b):
    return torch.from_numpy(np.stack([t[0] for t in b]))[:, None], [t[1] for t in b]


def rec_train(a):
    from o2gauge.dialtext_models import TextRec

    files = load_bgs()

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if dev.type == "cuda":
        torch.cuda.set_per_process_memory_fraction(a.vram)
    print("device", dev, torch.cuda.get_device_name(0) if dev.type == "cuda" else "", flush=True)
    rec = TextRec(n_class=len(DIG_CHARS) + 1).to(dev)
    out = Path(a.out_dir)
    if a.resume and (out / "digit_rec.pt").exists():
        rec.load_state_dict(torch.load(out / "digit_rec.pt", map_location=dev))
    opt = torch.optim.AdamW(rec.parameters(), lr=a.lr, weight_decay=1e-4)
    warm = 300
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda i: min(1.0, (i + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(i, a.iters) / a.iters)) + 0.01)
    ctc = torch.nn.CTCLoss(blank=0, zero_infinity=True)

    vrng = np.random.default_rng(999)
    vbgs = [cv2.imread(str(f)) for f in files[::7]]
    vbgs = [b for b in vbgs if b is not None]
    vx, vt = [], []
    while len(vx) < 1024:
        x, lab = rec_sample(vrng, vbgs[int(vrng.integers(len(vbgs)))])
        if x is not None:
            vx.append(x)
            vt.append(lab)
    vx = torch.from_numpy(np.stack(vx))[:, None]
    print("val ready", len(vt), flush=True)

    def decode(lg):
        best = lg.argmax(-1).cpu().numpy()
        res = []
        for row in best:
            s, prev = [], 0
            for k in row:
                if k != prev and k != 0:
                    s.append(DIG_CHARS[k - 1])
                prev = k
            res.append("".join(s))
        return res

    @torch.no_grad()
    def evaluate():
        rec.eval()
        pred = []
        for i in range(0, len(vt), a.batch):
            ch = vx[i:i + a.batch]
            pred += decode(rec(ch.to(dev)))
        rec.train()
        return float(np.mean([p == t for p, t in zip(pred, vt)]))

    dl = DataLoader(RecSynth(a.seed, [str(f) for f in files]), batch_size=a.batch, num_workers=a.workers, collate_fn=collate,
                    persistent_workers=True, prefetch_factor=4)
    best, it, t0, lr_ = -1.0, 0, time.time(), 0.0
    for x, labels in dl:
        tgt_l = [encode_digits(s) for s in labels]
        lg = rec(x.to(dev, non_blocking=True)).float()
        lp = lg.log_softmax(-1).permute(1, 0, 2)
        tgt = torch.tensor([c for l in tgt_l for c in l], dtype=torch.long)
        il = torch.full((len(tgt_l),), lp.shape[0], dtype=torch.long)
        tl = torch.tensor([len(l) for l in tgt_l], dtype=torch.long)
        loss = ctc(lp.cpu(), tgt, il, tl).to(dev)                      # CTC on CPU (fast on ROCm)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(rec.parameters(), 5.0)
        opt.step()
        sched.step()
        lr_ = 0.98 * lr_ + 0.02 * loss.item()
        it += 1
        if a.pause:
            time.sleep(a.pause)
        if it % 100 == 0:
            el = time.time() - t0
            print(f"it {it} loss {lr_:.3f} lr {sched.get_last_lr()[0]:.2e} {it / el:.2f} it/s "
                  f"eta {(a.iters - it) / (it / el) / 60:.0f} min", flush=True)
        if it % 1000 == 0 or it == a.iters:
            acc = evaluate()
            print(f"VAL it {it}: exact string {acc:.3f}", flush=True)
            torch.save(rec.state_dict(), out / "digit_rec_last.pt")
            if acc > best:
                best = acc
                torch.save(rec.state_dict(), out / "digit_rec.pt")
                print("  saved best", flush=True)
        if it >= a.iters:
            break
    print("done best", best, flush=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("det-data")
    d.add_argument("--out", default="C:/o2data/digital_det")
    d.add_argument("--n", type=int, default=8000)
    d.add_argument("--seed", type=int, default=31)
    x = sub.add_parser("det-extra")
    x.add_argument("--out", default="C:/o2data/digital_det")
    x.add_argument("--n", type=int, default=3000)
    x.add_argument("--seed", type=int, default=31)
    ng = sub.add_parser("det-neg")
    ng.add_argument("--out", default="C:/o2data/digital_det")
    ng.add_argument("--n", type=int, default=1200)
    ng.add_argument("--seed", type=int, default=31)
    t = sub.add_parser("det")
    t.add_argument("--data", default="C:/o2data/digital_det/data.yaml")
    t.add_argument("--model", default="yolo26n.pt")
    t.add_argument("--epochs", type=int, default=40)
    t.add_argument("--batch", type=int, default=16)
    t.add_argument("--workers", type=int, default=4)
    t.add_argument("--pause", type=float, default=0.03)
    t.add_argument("--vram", type=float, default=0.7)
    r = sub.add_parser("rec")
    r.add_argument("--iters", type=int, default=12000)
    r.add_argument("--batch", type=int, default=128)
    r.add_argument("--workers", type=int, default=6)
    r.add_argument("--lr", type=float, default=2e-3)
    r.add_argument("--seed", type=int, default=5)
    r.add_argument("--pause", type=float, default=0.02)
    r.add_argument("--vram", type=float, default=0.6)
    r.add_argument("--resume", action="store_true")
    r.add_argument("--out-dir", default=str(ROOT / "vision/models"))
    a = ap.parse_args()
    {"det-data": det_data, "det-extra": det_extra, "det-neg": det_neg, "det": det_train, "rec": rec_train}[a.cmd](a)


if __name__ == "__main__":
    main()
