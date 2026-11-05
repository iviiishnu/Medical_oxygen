# O2 Monitor: camera-based oxygen pressure monitor

A camera (planned: an Android tablet) mounted in front of a hospital's main oxygen supply panel reads the analog
pressure gauge **and** the panel's status lamps with its camera, about once per second. When pressure
drops, it alarms locally and alerts staff phones and the nursing-station desktop.

> **This is a monitoring aid on top of the hospital's existing alarm panel, not a replacement for it.**
> It must never fail silently: if the camera cannot read the gauge, that is itself an alert.

> **Current focus: the vision model on a PC.** The Android app has been taken out of this repo for
> now while it is redesigned. It is still in the git history (commit `8011e1d` and earlier). The
> tablet parts of the diagram below are the planned design.

```
 Tablet at the oxygen panel (works with NO internet)                 Firebase (2nd layer)
 ┌───────────────────────────────────────────────────────────┐      ┌──────────────────────────┐
 │ Camera 1 frame/s ─► Stage A (classical CV)  ─┐            │      │ Firestore: live, history,│
 │ (focus+exposure  ─► Stage B (YOLO pose,     ─┼► Fusion ─► │ ───► │ alerts, heartbeats       │
 │  locked)              TFLite keypoints)      │  Alert     │      │ Functions: push, 2-min   │
 │                  ─► Lamp reader (HSV)  ──────┘  engine    │      │ escalation, TABLET_OFFLINE│
 │                     Local alarm (sound+flash) ◄─┘         │      └──────┬───────────┬───────┘
 └───────────────────────────────────────────────────────────┘             ▼           ▼
                                                              Staff phones (full-   Desktop dashboard
                                                              screen alarm + ACK)   (live, 24 h chart, log)
```

## Results so far

Tested on 200 held-out camera frames per dial, rendered from the **real panel photos** with glare,
blur, noise and JPEG artefacts added. None of these frames were used in training.

| Gauge | Method | Mean error | Worst | Within 0.2 kg/cm² |
|---|---|---|---|---|
| Alarm box 0–16 kg/cm² | Stage A (classical) | 0.039 | 0.14 | 100 % |
| | Stage B (model) | 0.056 | 0.22 | 99.5 % |
| | **Fused (shipped)** | **0.035** | **0.14** | **100 %** |
| Magnate 0–10 kg/cm² | Stage A | 0.024 | 0.09 | 100 % |
| | Stage B | 0.031 | 0.12 | 100 % |
| | **Fused (shipped)** | **0.022** | **0.09** | **100 %** |

The plan's targets are a mean error of 0.2 kg/cm² or less and a worst case of 0.5 or less.
Lamp state: 99.3–100 % on synthetic frames, and both real panels read correctly.
Alert logic: 19 scenarios pass in the Python reference engine.
Model speed: about 8 ms (ONNX) / 75 ms (TFLite, 1 thread) per frame on a desktop CPU.

**Automatic reader (no calibration)**: 312 of 312 NORMAL/ABNORMAL verdicts were correct on the stress test
(both panels, 12 needle values, lamps green/red/off, 11 camera conditions). The mean reading error was
0.03 kg/cm² and the worst was 0.17. See [`docs/eval_auto.json`](docs/eval_auto.json).

**Not yet validated on real hardware.** These numbers use frames *synthesised* from two real photos.
The physical test rig and hospital photos/videos are still to do (see [Status](#status)).
Full report: [`docs/eval_final.json`](docs/eval_final.json).

## Try it in 5 minutes (any laptop, no graphics card)

You only need **Python 3.12 or newer** ([python.org](https://www.python.org/downloads/); on Windows tick
"Add python.exe to PATH" during install). The trained model is already in the repo, so there is
nothing to train. It runs on the normal CPU, so no graphics card is needed.

```bash
git clone https://github.com/mithun2k51124/o2.git
cd o2
python -m pip install -r vision/requirements-run.txt   # numpy, opencv, onnxruntime, flask (~100 MB)
python vision/tools/tester_app.py
```

1. Open **http://127.0.0.1:8000** in a browser.
2. Drag a gauge photo onto the page. To start, use `samples/real/alarm_box.jpg` or
   `samples/real/magnate.jpg`. You can also paste one with Ctrl+V or drop several at once.
3. After about 2 seconds the page shows:
   * **NORMAL** (green) or **ABNORMAL** (red), or **CAN'T TELL**;
   * a **confidence %**;
   * the pressure reading;
   * the lamp colours it saw;
   * the photo with the dial, needle and lamps marked.

Nothing has to be clicked on the gauge. The dial, its scale and the lamps are found automatically.

| Photo | Expected result |
|---|---|
| `samples/real/alarm_box.jpg` | NORMAL, about 5.0 kg/cm² (scale 0–16) |
| `samples/real/magnate.jpg` | NORMAL, about 4.5 kg/cm² (scale 0–10) |

The page uses one photo at a time and stays on your computer. Stop it with Ctrl+C in the terminal.

Live from a webcam instead: `python vision/tools/live_webcam.py`. In the webcam window, **R** searches again,
**F** freezes, **S** saves a snapshot and **Q** quits.

Speed: about 2 s per photo and about 0.1 s per webcam frame, measured on a desktop CPU. Expect a few seconds
per photo on a basic laptop.

> **Training needs a graphics card. Running does not.** The GPU was only used once, to train the model.

## Repository layout

| Folder | What it is |
|---|---|
| `vision/` | Python: Stage A reader, lamp reader, fusion, reference alert engine, synthetic + photo-based data generator, training/eval/export tools, tests |
| `vision/models/` | Trained keypoint model: `gauge_pose.pt`, `.onnx`, `_fp32.tflite`, `_fp16.tflite` |
| `firebase/` | Firestore rules + indexes, Cloud Functions (push, escalation, heartbeat watchdog), admin scripts, emulator tests |
| `dashboard/` | Nursing-station web dashboard (React + Vite + Firebase), with a demo mode |
| `contract/` | Single source of truth shared by all parts: reading JSON schema, default thresholds, alert test scenarios, parity fixtures and Stage B spec (for a future app port) |
| `samples/real/` | The two real panel photos with their calibration and needle geometry |
| `docs/` | Setup guide, architecture, dataset survey, questions for the hospital, evaluation reports |

## Quick start

### 0. Prerequisites

| Tool | Version | Used for |
|---|---|---|
| Git | any | cloning |
| Python | 3.12+ (tested 3.14) | vision code, tests, dataset, training |
| Node.js | 20+ (tested 24) | Cloud Functions, dashboard, Firebase CLI |
| JDK | **21** for the Firebase emulators | backend tests |
| GPU (optional) | NVIDIA (CUDA) or AMD RX 6000/7000 (ROCm) | **training only**; running the model never needs one |

```bash
git clone https://github.com/mithun2k51124/o2.git
cd o2
```

### 0. Quick test: drop a photo, get NORMAL / ABNORMAL (no calibration)

```bash
python -m pip install -r vision/requirements-run.txt
python vision/tools/tester_app.py          # open http://127.0.0.1:8000 and drag photos onto the page
python vision/tools/auto_read.py photo.jpg # same from the command line (folder = batch)
python vision/tools/live_webcam.py         # live from a webcam
curl -F image=@photo.jpg http://127.0.0.1:8000/api/read     # HTTP API for another program
```
Everything is found automatically (`vision/o2gauge/auto.py`):
* **dial(s):** circle proposals refined by the keypoint model until its predicted centre and size
  stop moving; bezels, lamps and labels don't settle and are rejected;
* **gauge type, and so its scale:** the dial face is matched against the reference photos in
  `samples/real/` (alarm box 0–16, Magnate 0–10). An unrecognised dial is flagged and the
  confidence drops. Add a new gauge type by adding `name.jpg` + `name.calibration.json` there;
* **lamps:** lit = strongly coloured *and* brighter than its surroundings (or white-hot centre),
  so printed labels, paint and unlit lamps are ignored. Green = normal, red = low/alarm, amber = high;
* **verdict + confidence %:** needle vs the low limit (classical + model, less sure near the
  limit) combined with the lamp colour. Any red/amber lamp or low needle → ABNORMAL; if needle and
  lamp disagree it says so with ≤ 50 % confidence.

Stress test (needle moved to 12 values per panel, lamps green/red/off, 11 camera conditions):
`python vision/tools/eval_auto.py` → `docs/eval_auto.json`.

### 1. Vision: read a gauge photo (no training needed)

```bash
python -m pip install -r vision/requirements.txt
# Stage A + lamps + Stage B on the real photo -> JSON reading + debug image
python vision/tools/read_gauge.py samples/real/alarm_box.jpg samples/real/alarm_box.calibration.json \
       --model vision/models/gauge_pose.onnx --debug-dir out/
# Calibrate your own photo (click centre, rim, 0 mark, max mark, lamp corners; press s to save)
python vision/tools/calibrate.py my_panel.jpg my_panel.calibration.json --max 16 --lamps LOW:red,NORMAL:green
```

Output (one JSON message per frame, schema in `contract/reading.schema.json`):
```json
{"device_id": "tab-main-o2-01", "gauge_id": "oxygen_main", "ts": "2026-11-05T13:10:02+05:30",
 "value": 4.98, "unit": "kg/cm2", "confidence": 0.97, "lamp_state": "NORMAL", "method_agree": true, "status": "OK"}
```

### 2. Firebase backend

```bash
cd firebase
npm install && (cd functions && npm install)
npm run test:rules        # needs JDK 21 on PATH
npm run test:e2e          # alert -> push -> escalation -> acknowledge; tablet offline -> resolved
npx firebase login
npx firebase use --add    # your project
npm run deploy            # rules, indexes, functions
node scripts/set_role.js --email tablet01@hospital.org --role device --device tab-main-o2-01
node scripts/set_role.js --email nurse1@hospital.org  --role staff --name "Nurse 1" --order 1
node scripts/send_test_alert.js --token <FCM token>   # push test to one phone
```

### 3. Dashboard

```bash
cd dashboard
npm install
npm run dev               # http://localhost:5173: DEMO mode with simulated data
cp .env.example .env.local   # fill in your Firebase web config for live data
npm run build && (cd ../firebase && npx firebase deploy --only hosting)
```

Step-by-step setup, including the laptop test and the Firebase console clicks, is in
**[docs/SETUP.md](docs/SETUP.md)**.

## Training the keypoint model (Stage B)

**When to retrain:** the model is already trained, and more training on the same 2 photos won't
improve it. Retrain when real photos from the panel (new gauge models, hospital lighting, the real
camera angle) give wrong readings in the tester. Add those photos as described at the end of this
section, rebuild the dataset and train again. The new model is the same size and still runs on a CPU.
Adding a new gauge *type* for the auto reader usually needs no retraining, only
`name.jpg` + `name.calibration.json` in `samples/real/`.

The camera is fixed and the gauge geometry is known, so instead of one big "photo → number" network the
model finds 4 keypoints (**centre, needle tip, zero mark, max mark**), and the value follows from geometry.
Training data is generated from the real photos: the needle and its shadow are cut out, the dial
behind them is inpainted, and the needle is redrawn at every value with glare, blur, noise, JPEG and
camera-shift augmentation.

```bash
# 1. dataset: 5,400 train / 600 val / 400 held-out test (about 5 min)
python vision/tools/make_dataset.py --n 6000
python vision/tools/show_labels.py data/gauge_pose/images/train labels.jpg   # check the labels visually

# 2. train YOLO26n-pose (60 epochs)
python vision/tools/train_pose.py --device 0 --batch 64     # NVIDIA GPU (CUDA)
python vision/tools/train_pose.py --device cpu --batch 32   # CPU (~6.5 min per epoch)
```

**AMD GPU on Windows (tested on an RX 6600, ~35 s per epoch).** Use AMD's ROCm nightly PyTorch in a
separate Python 3.12 environment:
```bash
python -m pip install uv
python -m uv venv --python 3.12 .tools/rocm-venv
python -m uv pip install --python .tools/rocm-venv/Scripts/python.exe \
  --index-url https://nightly.repo.amd.com/rocm/whl-next/ --extra-index-url https://pypi.org/simple \
  --index-strategy unsafe-best-match "torch[device-gfx1032]" "torchvision[device-gfx1032]"
python -m uv pip install --python .tools/rocm-venv/Scripts/python.exe ultralytics==8.4.173 opencv-python
.tools/rocm-venv/Scripts/python.exe vision/tools/train_pose.py --device 0 --batch 64
```
(`gfx1032` = RX 6600/6650. Use your card's target, e.g. `gfx1030` for RX 6800/6900 or `gfx1100` for RX 7900.)

```bash
# 3. accuracy report on held-out frames from the real photos
python vision/tools/eval_model.py --model vision/models/gauge_pose.pt --json docs/eval_final.json

```
The tester page, `auto_read.py` and the webcam use `vision/models/gauge_pose.onnx`, which
`train_pose.py` writes. They pick up a new model as soon as they are restarted.

Optional, for a future mobile app: export to TFLite and refresh the parity fixtures.
```bash
# Python 3.12 env; Ultralytics' own LiteRT export is Linux/macOS-only, so this goes ONNX -> onnx2tf
python -m uv venv --python 3.12 .tools/export-venv
python -m uv pip install --python .tools/export-venv/Scripts/python.exe -r vision/requirements-export.txt
.tools/export-venv/Scripts/python.exe vision/tools/export_tflite.py
python vision/tools/export_parity.py
.tools/export-venv/Scripts/python.exe vision/tools/export_stageb_parity.py
```

Adding new real photos: put `name.jpg`, `name.calibration.json` (from `calibrate.py`) and
`name.needle.json` (hub / tip / tail points and widths; see `samples/real/*.needle.json`) in
`samples/real/`. `make_dataset.py` picks up every such set automatically.

## Safety design

| Rule | How |
|---|---|
| Smoothing | median of the last 5 valid readings; one glare frame cannot raise or hide an alarm |
| Confirmation | LOW/CRITICAL only after 3 consecutive low readings (about 3 s at 1 frame/s) |
| Hysteresis | clears only above threshold + 0.2 for 3 readings; never clears on unreadable frames |
| Trend | least-squares fall rate over 60 s ≥ 0.5 kg/cm²/min → early warning |
| Cross-check | two independent needle methods + the panel's own lamp; disagreement → UNCERTAIN |
| Panel lamp | a confirmed LOW lamp raises LOW even if the needle disagrees (tuned toward alerting) |
| Fail-safe | no valid reading for 30 s, lamp OFF, camera blocked, or battery low → MONITORING_LOST |
| Local first | the tablet sounds and flashes itself; Firebase is only the second layer |
| Heartbeat | 2 missed heartbeats → TABLET_OFFLINE to every on-duty phone |
| Escalation | unacknowledged for 2 min → next tier of staff |
| Audit | reading every minute + a JPEG snapshot at every alert, stored on the tablet |

**Thresholds come from the hospital.** The defaults (LOW 3.5, CRITICAL 3.0 kg/cm²) are placeholders,
set per device in Firestore `devices/{id}.config`.

## Tests

| Suite | Command | Count |
|---|---|---|
| Python vision + alert engine + Stage B + auto reader | `python -m pytest vision/tests` | 86 |
| Auto reader stress test | `python vision/tools/eval_auto.py` | 312 cases |
| Cloud Functions logic | `cd firebase/functions && npm test` | 8 |
| Firestore rules | `cd firebase && npm run test:rules` | 11 |
| Functions end-to-end (emulators) | `cd firebase && npm run test:e2e` | 3 |
| Dashboard | `cd dashboard && npm test` | 5 |

## Status

| Phase | State |
|---|---|
| 0: research, Stage A, contract, questions | ✅ done (slide deck pending) |
| 1: data, calibration, alert engine, Firestore | ✅ done in software; physical test rig and 300 hand-labelled real frames still needed |
| 2: model, lamps, fusion, escalation, dashboard | ✅ done |
| 2b: automatic reader (no calibration), drop-a-photo tester, live webcam | ✅ done |
| 3: tablet/phone app | ⏸️ paused. The app was removed from the repo for a redesign; the vision model is tested on a PC for now |
| 4: hospital pilot and handover | ⏳ not started |

**Open questions for the hospital** are in [docs/phase0_hospital_collection_and_questions.md](docs/phase0_hospital_collection_and_questions.md):
the LOW/CRITICAL thresholds, the true readings of the two photos, the Magnate HIGH/LOW lamp colours,
Wi-Fi/power at the panel, and the escalation order.

## Team
Mithun (vision track) · Nandan (app & alerts track). Engineering-student project, Dec 2026 review.
