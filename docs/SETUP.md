# Setup guide: Oxygen Pressure Monitor

The system is a monitoring aid on top of the hospital's existing alarm panel, not a replacement for it.

The Android app (tablet Monitor mode and staff phones) is out of the repo for now while it is
redesigned. It is in the git history up to commit `8011e1d`.

```
vision/      Python: Stage A reader, lamps, fusion, alert engine (reference), synthetic data, training
firebase/    Firestore rules, Cloud Functions (push, escalation, heartbeat watchdog), scripts
dashboard/   Nursing-station web dashboard (React)
contract/    Shared JSON schema, config, alert test scenarios, parity fixtures, Stage B spec
```

## 0. Just test the model on a laptop (no Firebase, no tablet, no graphics card)
1. Install **Python 3.12+** from <https://www.python.org/downloads/>. On Windows, tick **Add python.exe to PATH**.
2. Get the code and install the four run-time packages:
   ```
   git clone https://github.com/mithun2k51124/o2.git
   cd o2
   python -m pip install -r vision/requirements-run.txt
   ```
3. Start the tester with `python vision/tools/tester_app.py`, then open **http://127.0.0.1:8000**.
4. Drag a gauge photo onto the page, for example `samples\real\alarm_box.jpg`. You get NORMAL / ABNORMAL, a confidence %, the reading and lamp colours.
5. Optional:
   * live webcam: `python vision/tools/live_webcam.py`;
   * command line: `python vision/tools/auto_read.py photo.jpg` (a folder works too);
   * another program can post photos with `curl -F image=@photo.jpg http://127.0.0.1:8000/api/read` and gets JSON back.

The model runs on the CPU. A graphics card is only needed for re-training (section 4).

## 1. Firebase project (one time, needs your Google account)
1. Go to <https://console.firebase.google.com>, click **Add project**, and name it `o2-monitor`. Choose the Blaze plan, which Cloud Functions require; the expected usage is far inside the free quota.
2. Turn on **Authentication → Email/Password**, **Firestore** (region `asia-south1`) and **Cloud Messaging**.
3. Under **Project settings → Your apps**:
   * (later, when the app returns) add an **Android** app with package `org.o2monitor` and keep its `google-services.json`;
   * add a **Web** app, and copy its config into `dashboard/.env.local` (see `.env.example`).
4. Under **Project settings → Service accounts → Generate new private key**, save the file outside the repo, then:
   `set GOOGLE_APPLICATION_CREDENTIALS=C:\keys\o2-monitor-sa.json`
5. Deploy the backend:
   ```
   cd firebase
   npx firebase login
   npx firebase use --add          (pick the project)
   npm run deploy                  (rules, indexes, functions)
   ```
6. Create the accounts in **Authentication → Users**, then give each one a role:
   ```
   node scripts/set_role.js --email tablet01@hospital.org --role device --device tab-main-o2-01 --name "Main O2 panel"
   node scripts/set_role.js --email nurse1@hospital.org  --role staff --name "Nurse 1" --order 1
   node scripts/set_role.js --email biomed@hospital.org  --role staff --name "Biomedical" --order 2
   node scripts/set_role.js --email you@college.edu      --role admin
   ```
   Escalation goes to everyone at `--order 1` first, then adds `--order 2` after 2 minutes, and so on.
7. Set the thresholds **from the hospital** in Firestore: `devices/tab-main-o2-01.config.low_threshold` and
   `critical_threshold`. The values 3.5 and 3.0 kg/cm² are only placeholders.

## 2. Camera placement (for photos and the future tablet)
* Mount the camera **slightly off-axis** so ceiling lights don't reflect into the lens.
* The dial should fill about a third of the frame height.
* Keep the lamps in view, at least 2.5 dial-widths away from the gauge.

## 3. Nursing-station dashboard
```
cd dashboard
npm install
npm run build
cd ../firebase && npx firebase deploy --only hosting
```
Open the hosting URL, sign in with a staff account, and click **Enable alarm sound** once. Browsers block sound until someone clicks. With no `.env.local` the dashboard runs in **DEMO** mode with simulated data.

## 4. Re-training the model on new photos or videos
Only retrain when real photos read wrong in the tester. Each new photo goes in `samples/real/` with:
* `name.calibration.json`: dial centre, rim, 0 and max marks, lamps. Make it with `python vision/tools/calibrate.py name.jpg samples/real/name.calibration.json --max 16`.
* `name.needle.json`: hub, tip and tail points and widths. There is no tool for this yet; copy one of the existing files and edit it.

`make_dataset.py` creates thousands of training images from each photo by moving the needle and adding glare, blur and tilt. Training needs a graphics card (or about 6.5 min per epoch on a CPU).
```
python vision/tools/make_dataset.py --n 6000                     # uses samples/real/*.jpg + .calibration.json + .needle.json
.tools\rocm-venv\Scripts\python.exe vision/tools/train_pose.py --device 0 --batch 64   # AMD RX 6600 via ROCm (about 35 s per epoch)
python vision/tools/eval_model.py --model vision/models/gauge_pose.pt
```
Restart the tester page to use the new model. TFLite export (`export_tflite.py`) is only needed for a future mobile app.

## 5. Tests
| What | Command |
|---|---|
| Python (vision + alert engine + auto reader) | `python -m pytest vision/tests` |
| Auto reader stress test (312 cases) | `python vision/tools/eval_auto.py` |
| Cloud Functions logic | `cd firebase/functions && npm test` |
| Firestore rules / functions end-to-end (needs JDK 21) | `cd firebase && npm run test:rules` / `npm run test:e2e` |
| Dashboard | `cd dashboard && npm test` |
