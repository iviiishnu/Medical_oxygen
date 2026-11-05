"""Contact sheet of dataset images with their keypoint labels drawn (label sanity check).

usage: python vision/tools/show_labels.py data/gauge_pose/images/train out.jpg [--n 24]
"""
import argparse
from pathlib import Path

import cv2
import numpy as np

COLORS = [(0, 255, 0), (255, 0, 255), (255, 255, 0), (0, 0, 255)]   # centre, tip, zero, max

ap = argparse.ArgumentParser()
ap.add_argument("images")
ap.add_argument("out")
ap.add_argument("--n", type=int, default=24)
a = ap.parse_args()
files = sorted(Path(a.images).glob("*.jpg"))[: a.n]
tiles = []
for f in files:
    img = cv2.imread(str(f))
    s = img.shape[0]
    lab = Path(str(f).replace("images", "labels")).with_suffix(".txt").read_text().split()
    v = list(map(float, lab))
    cx, cy, w, h = v[1:5]
    cv2.rectangle(img, (int((cx - w / 2) * s), int((cy - h / 2) * s)), (int((cx + w / 2) * s), int((cy + h / 2) * s)), (200, 200, 200), 1)
    k = np.array(v[5:]).reshape(4, 3)
    if k[0, 2] and k[1, 2]:
        cv2.line(img, (int(k[0, 0] * s), int(k[0, 1] * s)), (int(k[1, 0] * s), int(k[1, 1] * s)), (255, 0, 255), 1)
    for i, (x, y, vis) in enumerate(k):
        if vis:
            cv2.circle(img, (int(x * s), int(y * s)), 4, COLORS[i], -1)
    tiles.append(cv2.resize(img, (200, 200)))
while len(tiles) % 6:
    tiles.append(np.zeros_like(tiles[0]))
rows = [np.hstack(tiles[i:i + 6]) for i in range(0, len(tiles), 6)]
cv2.imwrite(a.out, np.vstack(rows))
print("wrote", a.out)
