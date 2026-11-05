"""Click-to-calibrate tool (desktop version of the tablet's calibration screen).

usage: python vision/tools/calibrate.py IMAGE OUT.json [--max 16] [--lamps NORMAL:green,LOW:red]

Clicks, in order (instructions are shown in the window title):
  1. dial centre
  2. a point on the dial rim (sets the radius)
  3. the 0 mark            4. the max mark
  5..  for each lamp: top-left corner then bottom-right corner of the lit area
Optional: press 'e' to add >=5 rim points for perspective correction, then 'e' again.
Keys: u = undo last click, s = save, q = quit without saving.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from o2gauge.calibration import Calibration, Lamp  # noqa: E402


def build(clicks, rim, args, lamps_spec, size):
    c, rimp, z, m = clicks[:4]
    lamps = []
    for i, (name, hue) in enumerate(lamps_spec):
        a, b = clicks[4 + 2 * i], clicks[5 + 2 * i]
        x0, y0 = min(a[0], b[0]), min(a[1], b[1])
        lamps.append(Lamp(name, [int(x0), int(y0), int(abs(a[0] - b[0])), int(abs(a[1] - b[1]))], hue))
    return Calibration(center=list(c), radius=math.dist(c, rimp), zero_point=list(z), max_point=list(m),
                       min_value=args.min, max_value=args.max, unit=args.unit, device_id=args.device,
                       gauge_id=args.gauge, image_size=list(size), needle_color=args.needle,
                       rim_points=[list(p) for p in rim] if len(rim) >= 5 else None, lamps=lamps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--min", type=float, default=0.0)
    ap.add_argument("--max", type=float, default=16.0)
    ap.add_argument("--unit", default="kg/cm2")
    ap.add_argument("--device", default="tab-main-o2-01")
    ap.add_argument("--gauge", default="oxygen_main")
    ap.add_argument("--needle", default="dark", choices=["dark", "red"])
    ap.add_argument("--lamps", default="NORMAL:green,LOW:red",
                    help="comma list NAME:hue, e.g. HIGH:amber,NORMAL:green,LOW:red ('' for none)")
    args = ap.parse_args()
    lamps_spec = [tuple(s.split(":")) for s in args.lamps.split(",") if s]
    img = cv2.imread(args.image)
    if img is None:
        sys.exit(f"cannot read {args.image}")
    steps = ["dial CENTRE", "a point on the dial RIM", "the 0 mark", f"the MAX mark ({args.max:g})"]
    for name, _ in lamps_spec:
        steps += [f"{name} lamp: top-left", f"{name} lamp: bottom-right"]
    clicks, rim, rim_mode = [], [], [False]
    win = "calibrate"

    def title():
        if rim_mode[0]:
            return f"RIM MODE: click points on the rim ({len(rim)}), 'e' to finish"
        if len(clicks) < len(steps):
            return f"click {steps[len(clicks)]}   (u=undo, e=rim points, q=quit)"
        return "done - press 's' to save"

    def on_mouse(ev, x, y, *_):
        if ev != cv2.EVENT_LBUTTONDOWN:
            return
        if rim_mode[0]:
            rim.append((x, y))
        elif len(clicks) < len(steps):
            clicks.append((x, y))

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, on_mouse)
    while True:
        vis = img.copy()
        for i, p in enumerate(clicks):
            cv2.circle(vis, p, 4, (0, 0, 255), -1)
            cv2.putText(vis, str(i + 1), (p[0] + 5, p[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        for p in rim:
            cv2.circle(vis, p, 3, (255, 0, 0), -1)
        if len(clicks) >= 2:
            cv2.circle(vis, clicks[0], int(math.dist(clicks[0], clicks[1])), (0, 255, 0), 1)
        cv2.imshow(win, vis)
        cv2.setWindowTitle(win, title())
        k = cv2.waitKey(30) & 0xFF
        if k == ord("q"):
            return
        if k == ord("u"):
            (rim if rim_mode[0] else clicks)[-1:] = []
        if k == ord("e"):
            rim_mode[0] = not rim_mode[0]
        if k == ord("s") and len(clicks) == len(steps):
            try:
                cal = build(clicks, rim, args, lamps_spec, img.shape[1::-1])
                cal.save(args.out)
            except ValueError as e:
                print("invalid calibration:", e, "- press u to fix clicks")
                continue
            print("saved", args.out)
            return


if __name__ == "__main__":
    main()
