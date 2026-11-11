"""Evaluate reading each dial's scale off the dial, on random synthetic gauges the models never saw.

usage:
    python vision/tools/eval_dialtext.py --n 300            # one dial per photo, true centre given (text + scale)
    python vision/tools/eval_dialtext.py --n 100 --panel    # 1-3 DIFFERENT gauges per photo, full auto reader
Writes docs/eval_dialtext.json / docs/eval_dialtext_panel.json.

scale correct  = the fitted scale gives every printed mark's true value at its true position (+-1.5 % of span)
reading error  = value at the TRUE needle angle (single) / full auto reading (panel), % of the span
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vision"))
from o2gauge.dialtext import DialTextReader, match_gas                 # noqa: E402
from o2gauge.dialtext_geom import dial_angle                           # noqa: E402
from o2gauge.dialtext_synth import C0, RC, DialRender, _ang_pt, _photo, degrade  # noqa: E402


def truth(rd: DialRender):
    s = rd.scales[0]
    fr = float(np.clip(rd.value_frac, 0, 1))
    lo, hi = rd.lo, rd.hi
    words = [it.text for it in rd.items if it.kind == "arc"] + [it.text for it in rd.items if it.kind == "word"]
    gas = next((match_gas(t) for t in words if match_gas(t)), None)
    marks = [(float(v), _ang_pt(rd._angle(f), 0.8 * RC)) for v, f in zip(s.values, s.frac)]
    return dict(lo=float(lo), hi=float(hi), value=float(lo + fr * (hi - lo)), unit=s.unit, gas=gas,
                n_scales=len(rd.scales)), marks, _ang_pt(rd.needle_angle, 0.8 * RC)


def to_photo(H, p):
    return cv2.perspectiveTransform(np.float64([[p]]), H)[0, 0]


def check_scale(f, marks, H, c, span):
    errs = [abs(f.value_at(dial_angle(c[0], c[1], *to_photo(H, p))) - v) / span for v, p in marks]
    return max(errs) <= 0.015, max(errs)


def eval_single(n, seed):
    rng = np.random.default_rng(seed)
    tr = DialTextReader()
    rows, t_ms = [], []
    while len(rows) < n:
        rd = DialRender(rng)
        rp = float(np.exp(rng.uniform(np.log(70), np.log(260))))
        photo, H, c, rad, _, _ = _photo(rd, rng, rp)
        photo, sig = degrade(photo, rng)
        if rd.scales[0].size * rad < max(7, 4.5 * sig):
            continue                                   # numbers too small / blurred for a person to read either
        t, marks, tip = truth(rd)
        t0 = time.perf_counter()
        dt = tr.read(photo, c[0], c[1], rad)
        t_ms.append((time.perf_counter() - t0) * 1000)
        span = t["hi"] - t["lo"]
        row = dict(truth=t, found=bool(dt.scales), gas=dt.gas, r_px=round(rad))
        if dt.scales:
            f = dt.scales[0]
            ok, err = check_scale(f, marks, H, c, span)
            v = f.value_at(dial_angle(c[0], c[1], *to_photo(H, tip)))
            row.update(lo=f.vmin, hi=f.vmax, scale_ok=ok, scale_err=round(err, 4), unit=f.unit,
                       conf=round(f.confidence, 3), labels=len(f.labels),
                       value=round(v, 4), value_err_pct=round(abs(v - t["value"]) / span * 100, 2))
        rows.append(row)
    return summarise(rows, t_ms), rows


def summarise(rows, t_ms):
    n = len(rows)
    found = [r for r in rows if r["found"]]
    ok = [r for r in found if r["scale_ok"]]
    conf_ok = [r for r in found if r["conf"] >= 0.3]
    unit_rows = [r for r in found if r["unit"]]
    gas_rows = [r for r in rows if r["truth"]["gas"]]
    errs = [r["value_err_pct"] for r in ok]
    return dict(
        n=n, ms_per_dial=round(float(np.mean(t_ms))) if t_ms else None,
        scale_found=round(len(found) / n, 3),
        scale_correct=round(len(ok) / n, 3),
        confident_and_wrong=round(sum(not r["scale_ok"] for r in conf_ok) / n, 3),
        unit_read_correct_when_given=round(sum(r["unit"] == r["truth"]["unit"] for r in unit_rows) / max(len(unit_rows), 1), 3),
        unit_given=round(len(unit_rows) / n, 3),
        gas_correct=round(sum(r["gas"] == r["truth"]["gas"] for r in gas_rows) / max(len(gas_rows), 1), 3),
        gas_wrong_name=round(sum(r["gas"] not in (None, r["truth"]["gas"]) for r in rows) / n, 3),
        reading_err_pct_median=round(float(np.median(errs)), 2) if errs else None,
        reading_err_pct_p95=round(float(np.percentile(errs, 95)), 2) if errs else None,
    )


# ----------------------------------------------------------------------------- panels
def make_panel(rng, k):
    """k different random gauges side by side, as one camera photo."""
    rds, tiles = [], []
    half = int(1.75 * RC)
    for _ in range(k):
        rd = DialRender(rng)
        img = np.asarray(rd.img)[:, :, ::-1]
        tiles.append(img[int(C0) - half:int(C0) + half, int(C0) - half:int(C0) + half])
        rds.append(rd)
    pan = np.concatenate(tiles, 1)
    rp = float(rng.uniform(70, 150))
    s = rp / RC
    pan = cv2.resize(cv2.GaussianBlur(pan, (0, 0), 0.45 / s), None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    pad = int(0.4 * rp)
    pan = cv2.copyMakeBorder(pan, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    centres = [(pad + (2 * i + 1) * half * s, pad + half * s) for i in range(k)]
    pan, sig = degrade(pan, rng)
    return pan, rds, centres, rp, s, pad, half


def eval_panel(n, seed):
    from o2gauge.auto import AutoReader
    from o2gauge.stage_b import KeypointReader
    rng = np.random.default_rng(seed)
    ar = AutoReader(KeypointReader(ROOT / "vision/models/gauge_pose.onnx"), library=ROOT / "samples/real")
    rows, t_ms = [], []
    for i in range(n):
        k = int(rng.integers(1, 4))
        pan, rds, centres, rp, s, pad, half = make_panel(rng, k)
        t0 = time.perf_counter()
        res = ar.read(pan)
        t_ms.append((time.perf_counter() - t0) * 1000)
        for j, (rd, c) in enumerate(zip(rds, centres)):
            t, marks, tip = truth(rd)
            span = t["hi"] - t["lo"]
            g = min(res["readings"], key=lambda g: math.dist(g.dial.center, c), default=None)
            row = dict(truth=t, panel=i, dials=k, found=False, r_px=round(rp))
            if g is not None and math.dist(g.dial.center, c) < 0.35 * rp:
                row["dial_found"] = True
                f = g.text.scales[0] if g.text is not None and g.text.scales else None
                row["found"] = f is not None and g.scale_source.startswith("read from the dial")
                row["gas"] = g.gas
                if row["found"]:
                    def H_of(p):                   # canvas -> panel photo
                        return np.float64([(p[0] - C0 + half + 2 * j * half) * s + pad, (p[1] - C0 + half) * s + pad])
                    errs = [abs(f.value_at(dial_angle(c[0], c[1], *H_of(p))) - v) / span for v, p in marks]
                    row.update(scale_ok=max(errs) <= 0.015, scale_err=round(max(errs), 4), unit=f.unit,
                               conf=round(f.confidence, 3), lo=f.vmin, hi=f.vmax, labels=len(f.labels))
                    if g.value is not None:
                        row["value"] = g.value
                        row["value_err_pct"] = round(abs(g.value - t["value"]) / span * 100, 2)
                    else:
                        row["value_err_pct"] = 100.0
            else:
                row["dial_found"] = False
                row["gas"] = None
            rows.append(row)
    rep = summarise(rows, t_ms)
    rep["dials_found"] = round(sum(r["dial_found"] for r in rows) / len(rows), 3)
    ok = [r for r in rows if r.get("scale_ok")]
    e = [r["value_err_pct"] for r in ok]
    rep["auto_reading_err_pct_median"] = round(float(np.median(e)), 2) if e else None
    rep["auto_reading_within_2pct"] = round(sum(x <= 2 for x in e) / len(rows), 3)
    rep["ms_per_photo"] = rep.pop("ms_per_dial")
    rep.pop("reading_err_pct_median")
    rep.pop("reading_err_pct_p95")
    return rep, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=2024)
    ap.add_argument("--panel", action="store_true")
    a = ap.parse_args()
    if a.panel:
        rep, rows = eval_panel(a.n, a.seed)
        out = ROOT / "docs/eval_dialtext_panel.json"
    else:
        rep, rows = eval_single(a.n, a.seed)
        out = ROOT / "docs/eval_dialtext.json"
    print(json.dumps(rep, indent=2))
    out.write_text(json.dumps({"summary": rep, "rows": rows}, indent=1, default=float))
    print("wrote", out)


if __name__ == "__main__":
    main()
