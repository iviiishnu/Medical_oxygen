# Public analog-gauge datasets (searched 5 Nov 2026)

Roboflow pages block automated download; sizes marked "check" must be read on the page
after logging in. Downloading from Roboflow needs your free API key (`ROBOFLOW_API_KEY`).

| Dataset | Labels | Size | Licence | Use for us |
|---|---|---|---|---|
| [Roboflow: gauge-wwktl/gauge-c7cja](https://universe.roboflow.com/gauge-wwktl/gauge-c7cja) | 11 classes incl. centre, tip, max, min (boxes around points) | check | Public Domain | **Best fit**: box centres become our 4 keypoints |
| [Roboflow: dataset-qxuat/analog-gauge-wj1r6](https://universe.roboflow.com/dataset-qxuat/analog-gauge-wj1r6) | centre, gauge, max, min, tip (boxes) | check | check | Same conversion as above |
| [Roboflow: gauge-wwktl/analog-gauge-reading](https://universe.roboflow.com/gauge-wwktl/analog-gauge-reading) | gauge reading | check | CC BY 4.0 (cite) | Pre-training |
| [Roboflow: m-zaid/pressure_gauge_key_points](https://universe.roboflow.com/m-zaid/pressure_gauge_key_points) | needle + gauge | check | CC BY 4.0 | Gauge detection only |
| [Roboflow: analog-guage-reader/analog-gauge-reader-xnvsn](https://universe.roboflow.com/analog-guage-reader/analog-gauge-reader-xnvsn) | centre, gauge, needle tip | 123 images (v2) | check | Small, but has tip + centre |
| [Roboflow: itu-weijie-wang/pointer-and-center-detection](https://universe.roboflow.com/itu-weijie-wang/pointer-and-center-detection) | pointer, centre | check | check | Pre-training |
| [Hugging Face: Synanthropic/reading-analog-gauge](https://huggingface.co/datasets/Synanthropic/reading-analog-gauge) | "corner" and "keypoint" sets | 10K-100K images | not stated (ask before use) | Synthetic pre-training, if the licence allows |
| Kaggle | nothing gauge-specific with keypoints found | - | - | - |

**Decision:** our own synthetic generator (`vision/o2gauge/synth.py`, and `photo_synth.py` once we have
Babu sir's photo) is the main training source, because it has exact labels for *our* dial.
Public sets are optional pre-training. `vision/tools/convert_roboflow.py` turns the
"centre/tip/min/max as boxes" format into our 4-keypoint YOLO-pose labels.
