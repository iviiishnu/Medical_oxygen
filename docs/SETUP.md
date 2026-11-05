# Setup guide: Oxygen Pressure Monitor

The system is a monitoring aid on top of the hospital's existing alarm panel, not a replacement for it.

```
vision/      Python: Stage A reader, lamps, fusion, alert engine (reference), synthetic data, training
android/     Kotlin app: Monitor mode (tablet) + Staff mode (phones)
firebase/    Firestore rules, Cloud Functions (push, escalation, heartbeat watchdog), scripts
dashboard/   Nursing-station web dashboard (React)
contract/    Shared JSON schema, config, alert test scenarios, parity fixtures, Stage B spec
```

## 1. Firebase project (one time, needs your Google account)
1. Go to <https://console.firebase.google.com>, click **Add project**, and name it `o2-monitor`. Choose the Blaze plan, which Cloud Functions require; the expected usage is far inside the free quota.
2. Turn on **Authentication → Email/Password**, **Firestore** (region `asia-south1`) and **Cloud Messaging**.
3. Under **Project settings → Your apps**:
   * add an **Android** app with package `org.o2monitor`, and download `google-services.json` to `android/app/`;
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

## 2. Tablet (Monitor mode)
1. Build the app: `cd android && gradlew assembleDebug` (with `google-services.json` in place). Then install it: `adb install app/build/outputs/apk/debug/app-debug.apk`.
2. Open the app, sign in as the tablet account, choose **MONITOR**, and allow camera and notifications. Allow "ignore battery optimisation" too.
3. Android will ask which home app to use. Pick **O2 Monitor → Always**, so monitoring restarts by itself after a reboot.
4. Mounting:
   * Fix the tablet **slightly off-axis** so ceiling lights don't reflect into the lens.
   * Keep it on a **charger** at all times.
   * The dial should fill about a third of the frame height.
5. Press **Calibrate**, choose the panel preset, and tap: centre, rim, 0 mark, max mark, then each lamp's corners. Press **Test reading**, and only press **Save** if it matches the gauge.
6. Test the full chain:
   * cover the camera: MONITORING LOST should sound within 30 s;
   * unplug Wi-Fi: the local alarm still works, and staff get TABLET OFFLINE within about 2 min.

## 3. Staff phones (Staff mode)
Install the same APK. Sign in with a staff account, choose **STAFF**, and allow notifications. Alarms arrive as a full-screen screen with a loud sound, even when the phone is locked. Press **ACKNOWLEDGE** to stop the alarm on every phone.

## 4. Nursing-station dashboard
```
cd dashboard
npm install
npm run build
cd ../firebase && npx firebase deploy --only hosting
```
Open the hosting URL, sign in with a staff account, and click **Enable alarm sound** once. Browsers block sound until someone clicks. With no `.env.local` the dashboard runs in **DEMO** mode with simulated data.

## 5. Re-training the model on new photos or videos
```
python vision/tools/make_dataset.py --n 6000                     # uses samples/real/*.jpg + .calibration.json + .needle.json
.tools\rocm-venv\Scripts\python.exe vision/tools/train_pose.py --device 0 --batch 64   # AMD RX 6600 via ROCm (about 35 s per epoch)
python vision/tools/eval_model.py --model vision/models/gauge_pose.pt
.tools\export-venv\Scripts\python.exe vision/tools/export_tflite.py
copy vision\models\gauge_pose_fp32.tflite android\app\src\main\assets\gauge_pose.tflite
python vision/tools/export_parity.py
.tools\export-venv\Scripts\python.exe vision/tools/export_stageb_parity.py    # then: gradlew testDebugUnitTest
```

## 6. Tests
| What | Command |
|---|---|
| Python (vision + alert engine) | `python -m pytest vision/tests` |
| Android JVM: alert scenarios, Kotlin vs Python parity, 24 h soak simulation | `cd android && gradlew testDebugUnitTest` |
| Cloud Functions logic | `cd firebase/functions && npm test` |
| Firestore rules / functions end-to-end (needs JDK 21) | `cd firebase && npm run test:rules` / `npm run test:e2e` |
| Dashboard | `cd dashboard && npm test` |
