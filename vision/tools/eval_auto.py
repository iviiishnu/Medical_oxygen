"""Stress test of the no-calibration auto reader on the two real panel photos.

The needle is moved to known values with the photo-based renderer (same as training data),
pasted back into the FULL photo, then the panel lamps are switched (lit green / lit red / off)
and camera problems are added. Every case has a known correct answer.

usage: python vision/tools/eval_auto.py [--quick] [--out docs/eval_auto.json] [--sheet out/auto_eval]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from o2gauge.auto import AutoReader, draw, find_lit_lamps   # noqa: E402
from o2gauge.config import MonitorConfig                     # noqa: E402
from o2gauge.photo_synth import load_photo_dial              # noqa: E402
from o2gauge.stage_b import KeypointReader                   # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PANELS = {"alarm_box": 16.0, "magnate": 10.0}


# ------------------------------------------------------------------ scene construction
def full_with_value(stem: str, dial, value: float) -> np.ndarray:
    full = cv2.imread(str(ROOT / f"samples/real/{stem}.jpg"))
    roi, _ = dial.render(value)
    x0, y0 = dial.offset
    full[y0:y0 + roi.shape[0], x0:x0 + roi.shape[1]] = roi
    return full


def set_lamps(img: np.ndarray, mode: str) -> np.ndarray:
    """mode: green (as photographed) | red (lit lamps turned red) | off (lit lamps switched off)."""
    if mode == "green":
        return img
    out = img.copy()
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV)
    for l in find_lit_lamps(img):
        if l.color != "green":
            continue
        x, y, w, h = l.box
        g = int(0.6 * max(w, h))
        x0, y0, x1, y1 = max(0, x - g), max(0, y - g), min(img.shape[1], x + w + g), min(img.shape[0], y + h + g)
        sub = hsv[y0:y1, x0:x1]
        green = (sub[..., 0] >= 36) & (sub[..., 0] <= 95) & (sub[..., 1] >= 40)
        if mode == "red":
            sub[..., 0][green] = 177
        else:                                       # off: dull, dark
            sub[..., 1][green] = (sub[..., 1][green] * 0.35).astype(np.uint8)
            sub[..., 2][green] = (sub[..., 2][green] * 0.45).astype(np.uint8)
        white = (sub[..., 2] > 225) & (sub[..., 1] < 60)    # lamp's blown-out centre
        if mode == "off":
            sub[..., 2][white] = 110
        hsv[y0:y1, x0:x1] = sub
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def camera(img: np.ndarray, kind: str, rng) -> np.ndarray:
    H, W = img.shape[:2]
    if kind == "clean":
        return img
    if kind == "far (50% size)":
        small = cv2.resize(img, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        canvas = np.full_like(img, int(np.median(img)))
        canvas[H // 4:H // 4 + small.shape[0], W // 4:W // 4 + small.shape[1]] = small
        return canvas
    if kind == "low-res 640px":
        return cv2.resize(img, (640, int(640 * H / W)), interpolation=cv2.INTER_AREA)
    if kind == "tilted 8deg":
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 8, 1.0)
        return cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REPLICATE)
    if kind == "perspective":
        src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
        dst = np.float32([[W * .06, H * .03], [W * .97, 0], [W, H], [W * .03, H * .95]])
        return cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (W, H), borderMode=cv2.BORDER_REPLICATE)
    if kind == "blur":
        return cv2.GaussianBlur(img, (0, 0), 2.5)
    if kind == "dark":
        return np.clip(img.astype(np.float32) * 0.45, 0, 255).astype(np.uint8)
    if kind == "bright":
        return np.clip(img.astype(np.float32) * 1.35 + 20, 0, 255).astype(np.uint8)
    if kind == "noise":
        return np.clip(img.astype(np.float32) + rng.normal(0, 12, img.shape), 0, 255).astype(np.uint8)
    if kind == "jpeg q25":
        return cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 25])[1], cv2.IMREAD_COLOR)
    if kind == "glare":
        yy, xx = np.mgrid[0:H, 0:W]
        cx, cy = W * rng.uniform(0.35, 0.65), H * rng.uniform(0.25, 0.5)
        g = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (0.07 * W) ** 2))[..., None]
        return np.clip(img.astype(np.float32) + 170 * g, 0, 255).astype(np.uint8)
    raise ValueError(kind)


CAMERAS = ["clean", "far (50% size)", "low-res 640px", "tilted 8deg", "perspective", "blur", "dark",
           "bright", "noise", "jpeg q25", "glare"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "docs/eval_auto.json"))
    ap.add_argument("--sheet", default=str(ROOT / "out/auto_eval"))
    ap.add_argument("--model", default=str(ROOT / "vision/models/gauge_pose.onnx"))
    ap.add_argument("--panel-model", default=None)
    a = ap.parse_args()
    cfg = MonitorConfig.load()
    reader = AutoReader(KeypointReader(a.model), cfg, panel_model=KeypointReader(a.panel_model) if a.panel_model else None)
    rng = np.random.default_rng(7)
    Path(a.sheet).mkdir(parents=True, exist_ok=True)
    rows = []
    t0 = time.perf_counter()
    for stem, vmax in PANELS.items():
        dial = load_photo_dial(ROOT / f"samples/real/{stem}")
        values = np.linspace(0.06, 0.94, 5 if a.quick else 12) * vmax
        for v in values:
            base = full_with_value(stem, dial, float(v))
            truth_bad = v < cfg.low_threshold
            lamp_modes = ["matched", "conflict", "off"]
            for lm in lamp_modes:
                if lm == "matched":
                    lamp = "red" if truth_bad else "green"
                elif lm == "conflict":
                    lamp = "green" if truth_bad else "red"
                else:
                    lamp = "off"
                scene = set_lamps(base, lamp)
                cams = CAMERAS if lm == "matched" else ["clean"]
                if a.quick:
                    cams = cams[:4]
                for cam in cams:
                    img = camera(scene, cam, rng)
                    r = reader.read(img)                  # no scale given: must recognise the gauge
                    m = r["main"]
                    expect = "ABNORMAL" if (truth_bad or lamp == "red") else "NORMAL"
                    got = r["verdict"]
                    found = m is not None and math.dist(m.dial.center, (
                        dial.cal.center[0] + dial.offset[0], dial.cal.center[1] + dial.offset[1])) < 0.3 * dial.cal.radius \
                        if cam in ("clean", "blur", "dark", "bright", "noise", "jpeg q25", "glare") else m is not None
                    err = None if m is None or m.value is None else abs(m.value - v)
                    rows.append({"panel": stem, "true_value": round(float(v), 2), "lamp": lamp, "lamp_case": lm,
                                 "camera": cam, "expect": expect, "verdict": got.verdict,
                                 "confidence": got.confidence, "correct": got.verdict == expect,
                                 "dial_found": bool(found), "gauge_type": None if m is None else m.gauge_type,
                                 "type_ok": m is not None and m.gauge_type == stem,
                                 "reading": None if m is None else m.value,
                                 "abs_err": None if err is None else round(err, 3),
                                 "lamps_seen": [l.color for l in r["lamps"]]})
                    if got.verdict != expect or (err is not None and err > 0.5):
                        fn = f"{stem}_{v:.1f}_{lamp}_{cam.replace(' ', '_').replace('%', '')}.jpg"
                        cv2.imwrite(str(Path(a.sheet) / fn), draw(img, r))
        print(f"{stem} done ({time.perf_counter() - t0:.0f}s)", flush=True)

    # ------------------------------------------------------------------ summary
    def summ(rs):
        errs = [r["abs_err"] for r in rs if r["abs_err"] is not None]
        ok = [r for r in rs if r["correct"]]
        return {"n": len(rs), "verdict_acc": round(len(ok) / max(1, len(rs)), 3),
                "dial_found": round(sum(r["dial_found"] for r in rs) / max(1, len(rs)), 3),
                "type_ok": round(sum(r["type_ok"] for r in rs) / max(1, len(rs)), 3),
                "mae": round(float(np.mean(errs)), 3) if errs else None,
                "worst": round(float(np.max(errs)), 3) if errs else None,
                "within_0.2": round(float(np.mean(np.array(errs) <= 0.2)), 3) if errs else None,
                "mean_conf_correct": round(float(np.mean([r["confidence"] for r in ok])), 3) if ok else None,
                "mean_conf_wrong": round(float(np.mean([r["confidence"] for r in rs if not r["correct"]])), 3)
                if len(ok) < len(rs) else None}

    summary = {"overall": summ(rows)}
    for p in PANELS:
        summary[p] = summ([r for r in rows if r["panel"] == p])
    for c in CAMERAS:
        rs = [r for r in rows if r["camera"] == c]
        if rs:
            summary[f"camera: {c}"] = summ(rs)
    for lm in ("matched", "conflict", "off"):
        summary[f"lamps: {lm}"] = summ([r for r in rows if r["lamp_case"] == lm])
    wrong = [r for r in rows if not r["correct"]]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"summary": summary, "wrong": wrong, "rows": rows}, indent=1))
    print(f"\n{'group':28s} {'n':>4s} {'verdict':>8s} {'found':>6s} {'type':>6s} {'MAE':>6s} {'worst':>6s} {'<=0.2':>6s} {'conf ok':>8s} {'conf bad':>8s}")
    for k, s in summary.items():
        f = lambda x: "-" if x is None else f"{x:.2f}"
        print(f"{k:28s} {s['n']:4d} {s['verdict_acc']:8.1%} {s['dial_found']:6.0%} {s['type_ok']:6.0%} {f(s['mae']):>6s} {f(s['worst']):>6s} "
              f"{f(s['within_0.2']):>6s} {f(s['mean_conf_correct']):>8s} {f(s['mean_conf_wrong']):>8s}")
    print(f"\n{len(wrong)} wrong verdicts; images of failures -> {a.sheet}; report -> {a.out}")


if __name__ == "__main__":
    main()
