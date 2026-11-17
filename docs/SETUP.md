# O2 Monitor setup

The application uses PostgreSQL as its only database and account store. The Python API is the only
component that connects to PostgreSQL; phones, tablets, and the dashboard use the API over HTTP(S).

## Local setup (native PostgreSQL, no Docker)

1. Install PostgreSQL for Windows, Python 3.12+, and Node.js 20+. Start the PostgreSQL Windows
   service (for example, `Start-Service postgresql-x64-18` from an elevated PowerShell). Verify it
   listens locally with `pg_isready -h 127.0.0.1 -p 5432` or `psql --version` and a connection test.
2. Connect as the PostgreSQL administrator using `psql -U postgres -d postgres`. Create the app
   role and database, then set the app role password:

```sql
CREATE ROLE o2_monitor LOGIN;
CREATE DATABASE o2_monitor OWNER o2_monitor;
\password o2_monitor
\q
```

   If the role or database already exists, skip its `CREATE` statement. Use `ALTER ROLE o2_monitor
   LOGIN;` if you need to restore the role's login permission. The `\password` command prompts
   securely for a password. Use that password in `DATABASE_URL`.
3. Copy `.env.postgres.example` to repository-root `.env`. Set `DATABASE_URL` to your local
   PostgreSQL connection, for example `postgresql://o2_monitor:<URL-ENCODED-PASSWORD>@127.0.0.1:5432/o2_monitor`,
   and replace `AUTH_SECRET` with a random value at least 32 characters long. `.env` is ignored by Git.
   `POSTGRES_PASSWORD` is only used by the optional Compose setup and is not needed for native
   PostgreSQL.
4. Install backend dependencies:

```powershell
python -m pip install -r vision/requirements-run.txt
```

5. Create the first administrator account. The command asks for the password twice and stores only a
   scrypt password hash in PostgreSQL:

```powershell
python vision/tools/create_staff_user.py --email admin@hospital.org --role admin --name "Hospital Admin"
```

Create staff accounts with `--role staff --order 1`. Use `--off-duty` for accounts excluded from
on-call escalation. Reset an account by running the command again for the same email.

6. In `mobile`, run `npm install` and `npm start`. This starts the vision/API server and Expo. Sign in
   with the PostgreSQL staff account. For an installable development APK, run
   `npm run build:dev:android`; use `npm run start:dev` when launching it.
7. For the dashboard, copy `dashboard/.env.example` to `dashboard/.env.local`, set
   `VITE_BACKEND_URL` to the Python API address, then run `npm install` and `npm run dev`.

Devices connect to the backend over Wi-Fi and never connect directly to PostgreSQL. For an EAS\ndevelopment build, set the public, reachable API URL as
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
