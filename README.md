# O2 Monitor: camera-based oxygen pressure monitor

A camera (planned: an Android tablet) mounted in front of a hospital's main oxygen supply panel reads the analog
pressure gauge **and** the panel's status lamps with its camera, about once per second. When pressure
drops, it alarms locally and updates the app and nursing-station dashboard while they are open.

> **This is a monitoring aid on top of the hospital's existing alarm panel, not a replacement for it.**
> It must never fail silently: if the camera cannot read the gauge, that is itself an alert.

> The mobile app in `mobile/` uses an Expo development build and streams camera snapshots to the
> Python model/API. PostgreSQL stores staff accounts and all monitoring data. Alerts are polled while
> clients are open; no external identity or push service is required. See [mobile setup](mobile/README.md).

```
 Mobile camera / desktop dashboard                  Python monitoring API
 ┌──────────────────────────────┐                  ┌──────────────────────────┐
 │ PostgreSQL-backed session    │ ───────────────► │ Vision model + REST API   │
 │ camera JSON / ack report     │                  │ heartbeat + escalation   │
 └──────────────────────────────┘                  └─────────────┬────────────┘
                                                                │
                                      ┌─────────────────────────┴───────────┐
                                      ▼                                     ▼
                            PostgreSQL system of record
                            users, devices, readings, alerts
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

**Automatic reader (no calibration)**, 11 Nov 2026 models: 309 of 312 NORMAL/ABNORMAL verdicts correct on the
stress test (both panels, 12 needle values, lamps green/red/off, 11 camera conditions); dial found and gauge
type recognised in 312/312. Mean reading error 0.07 kg/cm², worst 0.23. The 3 misses are the same borderline
case (true 3.52 vs the 3.50 limit, read 3.41-3.50 -> ABNORMAL at ~43 % confidence). See
[`docs/eval_auto.json`](docs/eval_auto.json).

| Test (11 Nov 2026) | Result |
|---|---|
| Real Magnate photo (by eye: O2 ~4.8, Air ~4.2, Vacuum ~575) | O2 4.77, Air 4.07-4.14, Vacuum 579 |
| Real alarm-box photo (by eye ~5.0) | 5.01 |
| Real panels re-projected, camera turned up to 35° (`docs/eval_angles.json`) | 87.5 % of readings within 0.2 of straight-on, 0 dials lost, 20/20 verdicts right |
| Digital displays, held-out synthetic scenes (`docs/eval_digital.json`) | display found 99.5 %, digits exact 95.5 % |
| Photos with no digital display (false alarms) | 0 of 56 |
| Real seven-segment LCD photos (blood-pressure monitor) | 19 % of numbers read - **not good enough yet** (very large digits are missed) |
| Unknown internet gauge photos (12) | dial found in 12/12 with the new model (3/12 before) |

Models: `gauge_pose.onnx` = general model (finds every dial, reads unknown gauges), `gauge_pose_panel.onnx`
= specialist for the two hospital panels (reads recognised gauges), `digital_det.onnx` + `digit_rec.onnx` =
digital displays. All run on a normal CPU.

### New (11 Nov 2026): smarter reader

* **Magnate scale fixed.** The Magnate pressure dials' arc ends at 150 psi = **10.55 kg/cm²**, not 10. The
  old setting made every Magnate reading about 5 % low (Medical Air 3.86 instead of about 4.2).
* **Any camera angle.** A dial seen from the side is an ellipse, so equal steps of the scale are no longer
  equal angles. Each dial's rim is now fitted (three concentric bands, consensus) and the dial is turned
  back into a circle before the needle is read. Test: the real panels re-projected as if the camera were
  turned up to 35° (`vision/tools/eval_angles.py`), see `docs/eval_angles.json`.
* **Many more gauge designs.** The keypoint model was retrained on 16,400 dials: the hospital panels, the
  Synanthropic *reading-analog-dial* set (34k labelled dials of many designs, MIT licence), generated gauges,
  and half of them seen at up to 40°. Ghost "dials" (circles between two gauges, round buttons) are
  rejected by a rim check.
* **Digital (seven-segment) displays.** New reader `vision/o2gauge/digital.py`: a display detector
  (YOLO nano) + a digit recogniser (CTC), both trained only on synthetic LCD / LED meters pasted into real
  photos at random angles. Tested on held-out scenes, on a public set of real LCD photos and on photos
  with no display (false alarms). See `docs/eval_digital.json`.
* **Scale reading.** For a gauge that matches no reference photo the printed numbers are read to find the
  scale; if they cannot be read, the result also shows the needle as **% of full scale** (exact even when
  the numbers are unknown).
* The tester shows every dial and display found, numbered left to right; `samples/demo/` has a ready
  demo set (`python vision/tools/make_demo_set.py` rebuilds it).

**Not yet validated on real hardware.** These numbers use frames *synthesised* from two real photos.
The physical test rig and hospital photos/videos are still to do (see [Status](#status)).
Full report: [`docs/eval_final.json`](docs/eval_final.json).

## About: the models

"The model" is really a small team of **6 small AI models**, each with one job, plus normal code for the
geometry, the lamps and the decision. **M = million parameters** (the numbers a model learns in training);
2.5 M is tiny - big image AI models have hundreds of millions or billions - so all of them run on a normal CPU.

| # | Model (`vision/models/`) | Size | Parameters | Its one job |
|---|---|---|---|---|
| 1 | `gauge_pose.onnx` (general) | 9.6 MB | 2.5 M | find every round dial and mark 4 points: centre, needle tip, zero mark, max mark |
| 2 | `gauge_pose_panel.onnx` (specialist) | 9.6 MB | 2.5 M | the same 4 points, trained on the two hospital panels, so more accurate on them |
| 3 | `digital_det.onnx` | 9.3 MB | 2.4 M | find digital (seven-segment) number displays |
| 4 | `digit_rec.onnx` | 6.4 MB | 1.7 M | read the digits inside a display, e.g. "4.82" |
| 5 | `dialtext_det.onnx` | 3.6 MB | 1.0 M | find the printed numbers around a dial (0, 2, 4 ... 16) |
| 6 | `dialtext_rec.onnx` | 6.5 MB | 1.7 M | read those printed numbers to work out an unknown gauge's scale |
| | **Total** | **about 45 MB** (about 23 MB as fp16 for a tablet) | **about 11.7 M** | |

**What runs for each photo** (tester page, `auto_read.py`, webcam):

| Step | Model |
|---|---|
| 1. Find all round dials | **1** and **2** both search; results merged so neither misses a dial |
| 2. Is it a gauge we know? (alarm box, Magnate oxygen / air / vacuum) | no model: the dial is matched against the reference photos in `samples/real/` |
| 3a. Known gauge: read the needle | **2** (panel specialist) |
| 3b. Unknown gauge: read the printed scale, then the needle | **5 + 6** for the numbers, **1** for the needle |
| 4. Digital displays | **3** finds them, **4** reads each one |
| 5. Camera-angle fix, lamps, NORMAL / ABNORMAL + confidence | no model: normal code (`vision/o2gauge/auto.py`) |

So the hospital panels are read by models **1 + 2** (plus **3 + 4** if a panel has a digital display);
**5 + 6** are only used for gauges the system has never seen.

**Android tablet:** these are "nano" networks made for phones. The older panel model, as TFLite, ran in
about 75 ms per frame on one desktop CPU thread; a mid-range tablet should need roughly 150-300 ms per model
pass (estimate, not yet measured on a device) - enough for the planned 1 reading per second. The first dial
search takes a few seconds on a tablet, after which the app only follows the dial. Still to do for the app:
convert the new models to TFLite (ONNX -> onnx2tf), port today's Python logic to Kotlin with parity tests,
and measure on a real tablet.

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
2. Drag a gauge photo onto the page. To start, use the ready demo set in `samples/demo/` (or
   `samples/real/*.jpg`). You can also paste one with Ctrl+V or drop several at once.
3. After a few seconds the page shows:
   * **NORMAL** (green) or **ABNORMAL** (red), or **CAN'T TELL**;
   * a **confidence %**;
   * every needle dial **and digital display** it found, numbered left to right, with gas, reading, scale and status;
   * the lamp colours it saw;
   * the photo with the dials, needles, displays and lamps marked.

Nothing has to be clicked on the gauge. The dials, their scales, digital displays and the lamps are found
automatically, also when the photo is taken at an angle.

| Photo | Expected result |
|---|---|
| `samples/real/alarm_box.jpg` | NORMAL, about 5.0 kg/cm² (scale 0–16) |
| `samples/real/magnate.jpg` | NORMAL, Oxygen about 4.8 kg/cm², Medical Air about 4.1, Vacuum about 580 mmHg (scale 0–10.55 = 150 psi) |
| `samples/demo/03..05_magnate_*deg.jpg` | NORMAL, about the same readings from 25–35° camera angles |
| `samples/demo/06_alarm_box_LOW_2.6_red_lamp.jpg` | ABNORMAL (needle about 2.5, red lamp) |
| `samples/demo/07_magnate_oxygen_7.5.jpg` | NORMAL, oxygen about 7.4 |
| `samples/demo/08_digital_meter_4.82.jpg` | NORMAL, digital display 4.82 next to the oxygen dial |
| `samples/demo/09_digital_meter_LOW_2.95.jpg` | ABNORMAL, digital display 2.95 |

The page uses one photo at a time and stays on your computer. Stop it with Ctrl+C in the terminal.

Live from a webcam instead: `python vision/tools/live_webcam.py` (add `--digital` to also read digital
displays, slower). In the webcam window, **R** searches again, **F** freezes, **S** saves a snapshot and **Q** quits.

Speed: about 4 s per photo on a desktop CPU (two keypoint models search for dials, plus the digital
reader); the webcam follows the main dial at several frames per second. Expect longer on a basic laptop.

> **Training needs a graphics card. Running does not.** The GPU was only used once, to train the model.

## Repository layout

| Folder | What it is |
|---|---|
| `vision/` | Python: Stage A reader, lamp reader, fusion, reference alert engine, synthetic + photo-based data generator, training/eval/export tools, tests |
| `vision/models/` | `gauge_pose.onnx/.pt` (general keypoint model: finds every dial, reads unknown gauges), `gauge_pose_panel.onnx/.pt` (specialist for the two hospital panels), `digital_det` + `digit_rec` (digital displays), `dialtext_det` + `dialtext_rec` (printed scale numbers), `gauge_pose_fp32/fp16.tflite` (older panel model for a future app) |
| `firebase/` | Retired legacy prototype; not used by builds, runtime, or setup |
| `dashboard/` | Nursing-station web dashboard (React + Vite + PostgreSQL API), with a demo mode |
| `mobile/` | Expo Android/iOS app; authenticated API client, camera reader, registration, alerts and reports |
| `contract/` | Single source of truth shared by all parts: reading JSON schema, default thresholds, alert test scenarios, parity fixtures and Stage B spec (for a future app port) |
| `samples/real/` | The real panel photos with their calibration and needle geometry (one per Magnate dial) |
| `samples/demo/` | Ready demo photos for the tester (rebuild: `python vision/tools/make_demo_set.py`) |
| `docs/` | Setup guide, architecture, dataset survey, questions for the hospital, evaluation reports |

## Quick start

### 0. Prerequisites

| Tool | Version | Used for |
|---|---|---|
| Git | any | cloning |
| Python | 3.12+ (tested 3.14) | vision code, tests, dataset, training |
| Node.js | 20+ | mobile app and dashboard |
| PostgreSQL | 16+ | shared application database (local Docker Compose or hosted PostgreSQL) |
| Docker Desktop | current | optional local PostgreSQL service |
| JDK | Required by local Android tooling only | native Android builds |
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
* **dial(s):** circle proposals refined by the keypoint models (general + panel specialist, results
  merged) until the predicted centre and size stop moving; a dial must also show a clean round rim, so
  ghosts between two gauges, buttons and lit lamps are rejected;
* **camera angle:** the dial rim's ellipse is fitted and the dial turned back into a circle before the
  needle is read (only when it is clearly tilted);
* **gauge type, and so its scale:** the dial face is matched against the reference photos in
  `samples/real/` (alarm box 0–16, Magnate 0–10.55 = 150 psi). Identical faces (Magnate oxygen / air)
  are told apart by bezel colour and left-to-right order. An unrecognised dial gets its scale from its
  printed numbers if they can be read, otherwise it is flagged ("?", plus % of full scale) and the
  confidence drops. Add a new gauge type by adding `name.jpg` + `name.calibration.json` there;
* **digital displays:** seven-segment LCD / LED meters are found and read (`vision/o2gauge/digital.py`);
  next to a needle gauge the dial stays the main reading;
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

### 2. PostgreSQL backend and staff login

Copy `.env.postgres.example` to `.env` at the repository root, set `POSTGRES_PASSWORD`, match it in
`DATABASE_URL`, and replace `AUTH_SECRET` with a random secret of 32+ characters. Then:

```powershell
docker compose up -d postgres
python -m pip install -r vision/requirements-run.txt
python vision/tools/create_staff_user.py --email admin@hospital.org --role admin --name "Hospital Admin"
```

Create additional staff accounts with the same command and `--role staff --order 1`. From `mobile`,
run `npm install`, then `npm start`. For an installable Android development build, run
`npm run build:dev:android`. The Python API creates/updates the PostgreSQL schema on first connection.

### 3. Dashboard

Copy `dashboard/.env.example` to `dashboard/.env.local`, set `VITE_BACKEND_URL` to the Python API,
then run `npm install` and `npm run dev`. Set `VITE_DEMO_MODE=true` to use the local simulator.

Step-by-step setup is in **[docs/SETUP.md](docs/SETUP.md)**.

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
The tester page, `auto_read.py` and the webcam use `vision/models/gauge_pose.onnx`. `train_pose.py`
copies the best weights to `vision/models/gauge_pose.pt`; export that to ONNX (command in the v2 section
below). They pick up a new model as soon as they are restarted.

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

### v2 model (many gauge designs, any angle) and the digital reader

Public data goes to `C:\o2data` (not in the repo): the Synanthropic `keypoint.zip` from
huggingface.co/datasets/Synanthropic/reading-analog-gauge (MIT) unzipped to `C:\o2data\keypoint`, and the
Roboflow-100 `gauge` photos (huggingface.co/datasets/Francesco/gauge-u2lwv, CC) in `C:\o2data\bg_gauge_rf`
(used as real backgrounds). The training scripts rest the GPU after every batch (`--pause`) and cap its
memory (`--vram`), so the card is never pinned at 100 %.
```bash
# analog keypoint model v2: 16,400 dials (panels 45 %, Synanthropic 30 %, generated 25 %; half tilted up to 40 deg)
python vision/tools/make_dataset.py --out C:/o2data/gauge_pose_v2 --n 16000 --synanthropic 0.3 --random 0.15 --procedural 0.1
.tools/rocm-venv/Scripts/python.exe vision/tools/train_pose.py --data C:/o2data/gauge_pose_v2/data.yaml \
    --model vision/models/gauge_pose.pt --epochs 30 --batch 32 --device 0 --workers 4 --name gauge_pose_v2 --pause 0.03 --vram 0.5 --lr0 0.003
.tools/export-venv/Scripts/python.exe -c "from ultralytics import YOLO; YOLO('vision/models/gauge_pose.pt').export(format='onnx', imgsz=320, opset=17)"

# digital reader: detector data (8,000 scenes + 3,000 close-up / multi-row + 1,200 printed-text negatives)
python vision/tools/train_digital.py det-data --out C:/o2data/digital_det --n 8000
python vision/tools/train_digital.py det-extra --n 3000
python vision/tools/train_digital.py det-neg --n 1200
.tools/rocm-venv/Scripts/python.exe vision/tools/train_digital.py det --epochs 35
.tools/rocm-venv/Scripts/python.exe vision/tools/train_digital.py rec --iters 5000     # synthetic strips, on the fly
.tools/export-venv/Scripts/python.exe vision/tools/export_digital.py rec
.tools/export-venv/Scripts/python.exe vision/tools/export_digital.py det

# tests
python vision/tools/eval_angles.py      # real panels, camera turned up to 35 deg
python vision/tools/eval_digital.py     # synthetic held-out + real LCD photos + false alarms
python vision/tools/eval_auto.py        # 312-case stress test
```

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
| Local first | the panel's existing alarm remains primary; app/dashboard polling provides an additional notification layer |
| Heartbeat | 2 missed heartbeats → TABLET_OFFLINE to every on-duty phone |
| Escalation | unacknowledged for 2 min → next tier of staff |
| Audit | reading every minute + a JPEG snapshot at every alert, stored on the tablet |

**Thresholds come from the hospital.** The defaults (LOW 3.5, CRITICAL 3.0 kg/cm²) are placeholders,
set for each registered gauge in PostgreSQL through the device registration flow.

## Tests

| Suite | Command | Count |
|---|---|---|
| Python vision + alert engine + Stage B + auto reader + digital + safety regressions | `python -m pytest vision/tests` | 130 |
| Auto reader stress test | `python vision/tools/eval_auto.py --panel-model vision/models/gauge_pose_panel.onnx` | 312 cases |
| Camera-angle test (real panels turned up to 35°) | `python vision/tools/eval_angles.py --panel-model vision/models/gauge_pose_panel.onnx` | 20 views |
| Digital reader (synthetic + real LCD + false alarms) | `python vision/tools/eval_digital.py` | 200 + 26 + 56 photos |
| PostgreSQL authentication and persistence | backend smoke checks against a configured PostgreSQL instance | not run here |
| Dashboard | `cd dashboard && npm test` | 5 |

## Status

| Phase | State |
|---|---|
| 0: research, Stage A, contract, questions | ✅ done (slide deck pending) |
| 1: data, calibration, alert engine, PostgreSQL backend | ✅ core software implemented; physical test rig and 300 hand-labelled real frames still needed |
| 2: model, lamps, fusion, escalation, dashboard | ✅ done |
| 2b: automatic reader (no calibration), drop-a-photo tester, live webcam | ✅ done |
| 2c: any camera angle, many gauge designs, digital displays, scale reading (11 Nov 2026) | ✅ done; training stopped early by low RAM (general model epoch 19/30, display detector 9/18) - can be resumed; real digital-gauge photos needed |
| 3: tablet/phone app | 🛠️ Expo development build, responsive UI, live camera snapshots, image upload, PostgreSQL API and in-app alert polling are configured; hardware/network validation remains |
| 4: hospital pilot and handover | ⏳ not started |

**Open questions for the hospital** are in [docs/phase0_hospital_collection_and_questions.md](docs/phase0_hospital_collection_and_questions.md):
the LOW/CRITICAL thresholds, the true readings of the two photos, the Magnate HIGH/LOW lamp colours,
Wi-Fi/power at the panel, and the escalation order.

**Known limits (vision):** real seven-segment LCD photos are read poorly so far (19 % of numbers on a
public blood-pressure-monitor set; very large digits are missed); a printed label can look like a digital
display when the panel is small in the photo (held back by a confidence gate); everything is validated on
photos / re-projections of two real panels, not yet on hospital video.

## Team
Mithun (vision track) · Nandan (app & alerts track). Engineering-student project, Dec 2026 review.
