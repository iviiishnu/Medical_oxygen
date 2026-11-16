# O2 Monitor setup

The application uses PostgreSQL as its only database and account store. The Python API is the only
component that connects to PostgreSQL; phones, tablets, and the dashboard use the API over HTTP(S).

## Local setup

1. Install Docker Desktop, Python 3.12+, and Node.js 20+.
2. Copy `.env.postgres.example` to repository-root `.env`. Set a strong `POSTGRES_PASSWORD`, use the
   same password in `DATABASE_URL`, and replace `AUTH_SECRET` with a random value at least 32
   characters long. `.env` is ignored by Git.
3. Start PostgreSQL and install backend dependencies:

```powershell
docker compose up -d postgres
python -m pip install -r vision/requirements-run.txt
```

4. Create the first administrator account. The command asks for the password twice and stores only a
   scrypt password hash in PostgreSQL:

```powershell
python vision/tools/create_staff_user.py --email admin@hospital.org --role admin --name "Hospital Admin"
```

Create staff accounts with `--role staff --order 1`. Use `--off-duty` for accounts excluded from
on-call escalation. Reset an account by running the command again for the same email.

5. In `mobile`, run `npm install` and `npm start`. This starts the vision/API server and Expo. Sign in
   with the PostgreSQL staff account. For an installable development APK, run
   `npm run build:dev:android`; use `npm run start:dev` when launching it.
6. For the dashboard, copy `dashboard/.env.example` to `dashboard/.env.local`, set
   `VITE_BACKEND_URL` to the Python API address, then run `npm install` and `npm run dev`.

The Compose database binds to `127.0.0.1:5432`. Devices connect to the backend over Wi-Fi and never
connect directly to PostgreSQL. For an EAS development build, set the public, reachable API URL as
the Expo development environment's `O2_BACKEND_URL`. Do not put `DATABASE_URL` or `AUTH_SECRET` in
the mobile/EAS environment. A cloud-built app cannot reach a database bound to a developer PC's
`127.0.0.1`; the backend needs to run on a host reachable by the device.

## Accounts and security

Accounts are provisioned directly in PostgreSQL with `create_staff_user.py`. Passwords are hashed
with scrypt. The API issues signed, expiring bearer sessions using `AUTH_SECRET`; deactivate a staff
account in PostgreSQL to revoke access immediately. Keep `AUTH_SECRET` and `DATABASE_URL` only on the
backend host. Use HTTPS when the API is reachable outside a trusted development network.

## Data stored in PostgreSQL

Staff accounts, registered panels and gauge settings, registration images, current readings,
one-minute reading history, alert evidence, acknowledgement reasons/resolutions/notes, and alert
state/escalation data are saved in PostgreSQL. Live camera reads return JSON; images are stored only
for registration or an alert event.

Alerts refresh in the app and dashboard while they are open. Background push notifications are not
enabled; they require a separate delivery service, which this PostgreSQL-only setup intentionally
does not configure.

## Environment variables

| Variable | Used by | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | Docker Compose | Local database password |
| `DATABASE_URL` | Python backend | PostgreSQL connection string |
| `AUTH_SECRET` | Python backend | Signs and validates staff sessions |
| `O2_BACKEND_URL` | EAS app build | Optional public API base URL; safe to bundle |
| `VITE_BACKEND_URL` | Dashboard | Python API base URL |

The API creates or upgrades its schema on first database connection. Use a private, TLS-enabled
PostgreSQL URL for a hosted database.
