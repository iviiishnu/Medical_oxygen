# Stage B (keypoint model) — port spec for Android

Reference implementation: `vision/o2gauge/stage_b.py` + `vision/o2gauge/dataset.py`.
The Kotlin port must reproduce it; `contract/parity/` verifies it.

## 1. Input crop
* Square around the **calibrated** dial centre `(cx, cy)` with side `2 * 1.4 * radius` (CROP_SCALE = 1.4).
* Affine image→input: `s = 320 / side`; `M = [[s, 0, 160 - s*cx], [0, s, 160 - s*cy]]`.
* Warp to **320 × 320**, bilinear, border = replicate.
* Channel order **RGB**, `float32`, value / 255. TFLite layout **NHWC** `[1,320,320,3]`
  (ONNX: NCHW `[1,3,320,320]`).
* int8 model: quantise with the input tensor's `(scale, zero_point)`.

## 2. Output
YOLO26 pose exports **end-to-end** (no NMS needed): `[1, 300, 18]`, each row
`x1 y1 x2 y2 conf cls  (kx ky kconf) × 4`. Some exports give coordinates normalised to 0..1 —
if every keypoint coordinate is ≤ 1.5, multiply x and y by 320.
Classic YOLO11 layout (`[1, 17, 2100]`, channels first: `cx cy w h conf (kx ky kconf)×4`) is
also accepted by `decode()`.
Keep the single row with the highest `conf`.

Keypoint order: **0 centre, 1 needle tip, 2 zero mark, 3 max mark.**

## 3. Back to image pixels
`p_img = Minv · p_input` with `Minv` the inverse of `M` (for this M: `x = (kx - 160)/s + cx`).

## 4. Value
`value_from_keypoints(centre, tip, zero, max, min_value, max_value, direction)`:
dial angle = `atan2(px - cx, -(py - cy))` in degrees mod 360 (clockwise from 12 o'clock);
`Scale(zero_angle, max_angle).value(tip_angle)` with the 4° end-stop tolerance (see Geometry.kt).

## 5. Confidence
`conf = det_conf * min(kconf[centre], kconf[tip])`;
if the predicted centre is more than `0.15 * radius` from the calibrated centre, multiply by
`max(0, 1 - (off - 0.15) / 0.15)`; if the tip is out of range (dead zone) multiply by 0.5.

## 6. Fusion
`Fusion.fuse(stageA, stageB, lampState, config)` — unchanged (stage B value wins when both are
confident and agree within `agree_tolerance`; disagreement → UNCERTAIN).

## 7. Timing target
≤ 100 ms per frame on the tablet (crop + model + post-processing). Use the GPU delegate when
available, else XNNPACK with 4 threads.
