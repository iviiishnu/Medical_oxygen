"""Live gauge reading from a webcam - fully automatic (no calibration clicks).

usage: python vision/tools/live_webcam.py [--camera 0] [--max 16]

Point the webcam at a gauge (or at a photo of the panel on a phone/monitor). The dial is found
by itself, its type (scale) is recognised, lamps are read by colour, and the verdict
NORMAL / ABNORMAL with a confidence % is shown live.
Keys: R = search for the dial again, F = freeze/unfreeze, S = save snapshot, Q / Esc = quit.
--max forces the scale end value instead of recognising the gauge.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from o2gauge.auto import AutoReader, _refine, draw, find_dials, DIAL_MIN_CONF   # noqa: E402
from o2gauge.stage_b import KeypointReader                                       # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WIN = "O2 gauge - live (auto)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--model", default=str(ROOT / "vision/models/gauge_pose.onnx"))
    ap.add_argument("--max", type=float, default=None)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--digital", action="store_true", help="also read seven-segment displays (slower: ~0.5 s/frame)")
    a = ap.parse_args()

    cap = cv2.VideoCapture(a.camera, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(a.camera)
    if not cap.isOpened():
        sys.exit(f"cannot open webcam {a.camera} - try --camera 1")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, a.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, a.height)

    panel = ROOT / "vision/models/gauge_pose_panel.onnx"
    reader = AutoReader(KeypointReader(a.model), cache_types=True, digital=a.digital,
                        panel_model=KeypointReader(panel) if panel.exists() else None)
    state = {"dials": [], "searching": False, "last_search": 0.0}
    lock = threading.Lock()

    def search(frame):
        ds = find_dials(frame, reader.model)
        if len(ds) > 1:                       # main gauge = a recognised type first (as in AutoReader.read)
            ds.sort(key=lambda d: 0 if reader._identify(frame, d)[0] else 1)
        with lock:
            state["dials"], state["searching"], state["last_search"] = ds, False, time.time()

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    frozen, fps, t_prev = None, 0.0, time.perf_counter()
    snap_dir = ROOT / "out/webcam_snapshots"
    while True:
        if frozen is None:
            ok, frame = cap.read()
            if not ok:
                print("webcam frame grab failed")
                break
        else:
            frame = frozen
        with lock:
            dials, searching = list(state["dials"]), state["searching"]
        # follow the main dial found so far (cheap: two model passes); other dials are only
        # read in the photo tester, live video keeps to the main gauge for speed
        tracked = []
        for d in dials[:1]:
            t = _refine(reader.model, frame, d.center[0], d.center[1], d.radius, steps=1)
            if t.det_conf >= DIAL_MIN_CONF:
                tracked.append(t)
        with lock:
            state["dials"] = tracked
        lost = not tracked
        if lost and not searching and time.time() - state["last_search"] > 0.7:
            with lock:
                state["searching"] = True
            threading.Thread(target=search, args=(frame.copy(),), daemon=True).start()
        r = reader.read(frame, a.max, dials=tracked)
        vis = draw(frame, r)
        now = time.perf_counter()
        fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-3)
        t_prev = now
        m = r["main"]
        lines = []
        if m is not None:
            lines.append(f"reading {m.value if m.value is not None else '--'}   classical {m.stage_a}   model {m.stage_b}")
            lines.append(f"gauge: {m.scale}")
        else:
            lines.append("looking for a dial ..." if searching or lost else "no dial")
        lines.append("lamps: " + (", ".join(l.color for l in r["lamps"]) or "none lit") + f"     {fps:.0f} fps")
        lines.append("R = search again   F = freeze   S = snapshot   Q = quit")
        y = vis.shape[0] - 14 - 26 * (len(lines) - 1)
        for s in lines:
            cv2.putText(vis, s, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 5, cv2.LINE_AA)
            cv2.putText(vis, s, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
            y += 26
        cv2.imshow(WIN, vis)
        k = cv2.waitKey(1) & 0xFF
        if k in (ord("q"), 27):
            break
        if k == ord("r"):
            with lock:
                state["dials"], state["last_search"] = [], 0.0
        elif k == ord("f"):
            frozen = None if frozen is not None else frame.copy()
        elif k == ord("s"):
            snap_dir.mkdir(parents=True, exist_ok=True)
            fn = snap_dir / time.strftime("snap_%Y%m%d_%H%M%S.jpg")
            cv2.imwrite(str(fn), frame)
            cv2.imwrite(str(fn.with_name(fn.stem + "_result.jpg")), vis)
            print("saved", fn)
        if cv2.getWindowProperty(WIN, cv2.WND_PROP_VISIBLE) < 1:
            break
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
