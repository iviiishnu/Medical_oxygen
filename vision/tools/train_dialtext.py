"""Train the dial-text detector + recogniser on random synthetic gauges (generated on the fly).

usage (AMD GPU, ROCm venv):
    .tools\\rocm-venv\\Scripts\\python.exe vision/tools/train_dialtext.py --iters 24000
then export to ONNX (export venv):
    .tools\\export-venv\\Scripts\\python.exe vision/tools/export_dialtext.py

Every step draws fresh random gauges (any range, fonts, colours, dual scales, bezel names,
blur / glare / low resolution), so the models never see the same dial twice.
"""
from __future__ import annotations

import argparse
import math
import os
import sys

os.environ.setdefault("MIOPEN_FIND_MODE", "FAST")        # AMD: don't exhaustively tune every kernel
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, IterableDataset, get_worker_info

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vision"))
from o2gauge.dialtext_geom import CHARS, REC_H, REC_W, encode_text   # noqa: E402
from o2gauge.dialtext_models import TextDet, TextRec                 # noqa: E402
from o2gauge.dialtext_synth import det_sample, make_scene, rec_samples  # noqa: E402

P_STRIPS = 0.22
REC_B = 128


class Synth(IterableDataset):
    def __init__(self, seed):
        self.seed = seed

    def __iter__(self):
        wi = get_worker_info()
        rng = np.random.default_rng([self.seed, wi.id if wi else 0, int(time.time() * 1e3) % 100000])
        while True:
            try:
                sc = make_scene(rng)
                img, m, boxes = det_sample(sc, rng, rng.random() < P_STRIPS)
                recs = rec_samples(img, boxes, rng)
            except Exception as e:                       # a rare degenerate random gauge: skip it
                print("gen error:", repr(e), flush=True)
                continue
            yield img, m, recs


def collate(batch):
    imgs = torch.from_numpy(np.stack([b[0][:, :, ::-1] for b in batch]).copy()).permute(0, 3, 1, 2)
    masks = torch.from_numpy(np.stack([b[1] for b in batch]))[:, None]
    recs = [r for b in batch for r in b[2]]
    rx = torch.from_numpy(np.stack([r[0] for r in recs]))[:, None] if recs else torch.zeros(0, 1, REC_H, REC_W)
    labels = [encode_text(r[1]) for r in recs]
    return imgs, masks, rx, labels, [r[1] for r in recs]


def det_loss(logit, m):
    bce = F.binary_cross_entropy_with_logits(logit, m, pos_weight=torch.tensor(3.0, device=m.device))
    p = torch.sigmoid(logit)
    inter = (p * m).sum((1, 2, 3))
    dice = 1 - (2 * inter + 1) / (p.sum((1, 2, 3)) + m.sum((1, 2, 3)) + 1)
    return bce + dice.mean()


def ctc_decode(logits):
    """greedy CTC: (B, T, C) -> list[str]"""
    best = logits.argmax(-1).cpu().numpy()
    out = []
    for row in best:
        s, prev = [], 0
        for k in row:
            if k != prev and k != 0:
                s.append(CHARS[k - 1])
            prev = k
        out.append("".join(s))
    return out


def norm(s):
    return s.replace("Â²", "2")


@torch.no_grad()
def evaluate(det, rec, val, dev):
    det.eval()
    rec.eval()
    tp = fp = fn = 0
    ok = tot = 0
    num_ok = num_tot = 0
    for imgs, masks, rx, labels, texts in val:
        p = torch.sigmoid(det(imgs.to(dev).float() / 255)) > 0.5
        m = masks.to(dev) > 0.5
        tp += (p & m).sum().item()
        fp += (p & ~m).sum().item()
        fn += (~p & m).sum().item()
        if len(texts):
            pred = []
            for i in range(0, len(texts), REC_B):         # fixed shapes only (see REC_B)
                ch = rx[i:i + REC_B]
                n = len(ch)
                if n < REC_B:
                    ch = torch.cat([ch, ch.new_zeros((REC_B - n,) + tuple(ch.shape[1:]))])
                pred += ctc_decode(rec(ch.to(dev)))[:n]
            for a, b in zip(pred, texts):
                b = "".join(c for c in norm(b) if c in CHARS)
                ok += a.lower() == b.lower()
                tot += 1
                if b.replace(".", "").replace("-", "").isdigit():
                    num_ok += a == b
                    num_tot += 1
    det.train()
    rec.train()
    f1 = 2 * tp / max(2 * tp + fp + fn, 1)
    return f1, ok / max(tot, 1), num_ok / max(num_tot, 1), num_tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=24000)
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--out", default=str(ROOT / "vision/models"))
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--amp", action="store_true")
    ap.add_argument("--log", type=int, default=100)
    a = ap.parse_args()
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("device", dev, torch.cuda.get_device_name(0) if dev.type == "cuda" else "", flush=True)
    out = Path(a.out)
    det, rec = TextDet().to(dev), TextRec().to(dev)
    if a.resume:
        det.load_state_dict(torch.load(out / "dialtext_det.pt", map_location=dev))
        rec.load_state_dict(torch.load(out / "dialtext_rec.pt", map_location=dev))
    params = list(det.parameters()) + list(rec.parameters())
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=1e-4)
    warm = 500
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda i: min(1.0, (i + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(i, a.iters) / a.iters)) + 0.01)
    scaler = torch.amp.GradScaler(enabled=a.amp)
    ctc = torch.nn.CTCLoss(blank=0, zero_infinity=True)

    # fixed validation set (same every run)
    vrng = np.random.default_rng(12345)
    vb = []
    for i in range(160):
        sc = make_scene(vrng)
        img, m, boxes = det_sample(sc, vrng, i % 5 == 4)
        vb.append((img, m, rec_samples(img, boxes, vrng)))
    val = [collate(vb[i:i + 16]) for i in range(0, len(vb), 16)]
    print("val ready", sum(len(v[4]) for v in val), "text crops", flush=True)

    dl = DataLoader(Synth(7), batch_size=a.batch, num_workers=a.workers, collate_fn=collate,
                    persistent_workers=True, prefetch_factor=4)
    best = -1.0
    t0 = time.time()
    ld = lr_ = 0.0
    it = 0
    tw = ts = 0.0
    tl0 = time.time()
    for imgs, masks, rx, labels, _ in dl:
        tw += time.time() - tl0
        tl1 = time.time()
        imgs, masks = imgs.to(dev, non_blocking=True).float() / 255, masks.to(dev, non_blocking=True)
        with torch.autocast(dev.type, enabled=a.amp):
            l1 = det_loss(det(imgs).float(), masks)
        loss = l1
        keep = [i for i, l in enumerate(labels) if len(l)]
        if keep:
            # FIXED recogniser batch (MIOpen re-tunes kernels for every new tensor shape)
            sel = np.resize(np.random.permutation(keep), REC_B)
            if True:
                rx = rx[torch.from_numpy(sel)].to(dev)
                labels = [labels[i] for i in sel]
                with torch.autocast(dev.type, enabled=a.amp):
                    lg = rec(rx).float()
                lp = lg.log_softmax(-1).permute(1, 0, 2)
                tgt = torch.tensor([c for l in labels for c in l], dtype=torch.long)
                il = torch.full((len(labels),), lp.shape[0], dtype=torch.long)
                tl = torch.tensor([len(l) for l in labels], dtype=torch.long)
                # CTC on the CPU: on ROCm MIOpen's CTC recompiles for every new label length and the
                # native GPU kernel takes ~1.5 s; the CPU one takes ~4 ms (gradients flow back to the GPU)
                l2 = ctc(lp.cpu(), tgt, il, tl).to(dev)
                loss = loss + l2
                lr_ = 0.98 * lr_ + 0.02 * l2.item()
        opt.zero_grad(set_to_none=True)
        scaler.scale(loss).backward()
        scaler.unscale_(opt)
        torch.nn.utils.clip_grad_norm_(params, 5.0)
        scaler.step(opt)
        scaler.update()
        sched.step()
        ld = 0.98 * ld + 0.02 * l1.item()
        it += 1
        ts += time.time() - tl1
        tl0 = time.time()
        if it % a.log == 0:
            el = time.time() - t0
            print(f"it {it} det {ld:.3f} rec {lr_:.3f} lr {sched.get_last_lr()[0]:.2e} "
                  f"{it / el:.2f} it/s (data wait {tw / it:.2f}s, step {ts / it:.2f}s) eta {(a.iters - it) / (it / el) / 60:.0f} min", flush=True)
        if it % 1000 == 0 or it == a.iters:
            f1, acc, nacc, nn_ = evaluate(det, rec, val, dev)
            score = f1 + acc
            print(f"VAL it {it}: det pixel F1 {f1:.3f}  rec exact {acc:.3f}  numbers exact {nacc:.3f} (n={nn_})",
                  flush=True)
            torch.save(det.state_dict(), out / "dialtext_det_last.pt")
            torch.save(rec.state_dict(), out / "dialtext_rec_last.pt")
            if score > best:
                best = score
                torch.save(det.state_dict(), out / "dialtext_det.pt")
                torch.save(rec.state_dict(), out / "dialtext_rec.pt")
                print("  saved best", flush=True)
        if it >= a.iters:
            break
    print("done", flush=True)


if __name__ == "__main__":
    main()
