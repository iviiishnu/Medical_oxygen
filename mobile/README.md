# O2 Monitor mobile app

Expo / React Native monitoring app for Android phones, Android tablets, iPhones, and iPads. PostgreSQL
is the only account and application database. The mobile app talks to the Python API; it never opens
a direct database connection.

## Features

- Responsive phone and tablet layouts with portrait/landscape support and dark theme.
- Live camera reader, photo capture, and image upload. Normal readings return JSON; evidence images
  are included for registration and alert events.
- Panel registration from an image, gauge selection/ignore controls, threshold configuration, alert
  acknowledgement reports, device history, and on-screen alert polling.
- PostgreSQL-backed staff sign-in. The backend issues expiring sessions; staff passwords are hashed
  in PostgreSQL.
- Optional local demo mode for the UI without a backend.

Alerts are polled from PostgreSQL while the app is open. Background push delivery is not configured;
it would require a separate service and is intentionally absent from this PostgreSQL-only setup.

## Start locally

Install and start PostgreSQL as a local Windows service (no Docker required). Create the `o2_monitor`
role and database, then configure the root `.env` from `.env.postgres.example` with the local
`DATABASE_URL` and a private `AUTH_SECRET`. Install backend dependencies:

```powershell
python -m pip install -r vision/requirements-run.txt
python vision/tools/create_staff_user.py --email nurse@hospital.org --role staff --name "Nurse 1" --order 1
```

The account command prompts for a password and stores a scrypt hash. Create an `admin` similarly for
administrator access. Then from `mobile`:

```powershell
npm install
npm start
```

`npm start` starts the model/API server and Expo. The device and backend computer need to share a
network. The app can discover the Expo computer on the LAN; for a fixed host, set `O2_BACKEND_URL`.
For an installable Android development build, run `npm run build:dev:android`, install the APK, then
run `npm run start:dev` while developing.

More database and network details are in [docs/SETUP.md](../docs/SETUP.md).
