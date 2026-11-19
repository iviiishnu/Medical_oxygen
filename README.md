# Oxygen Flow Check

A centralized web portal for monitoring medical-gas pressure gauges. A tablet
camera app (Mithun's model) reads the gauges and POSTs JSON to this portal,
which stores every reading, raises alarms when pressure goes critical, and
presents everything to monitoring staff in real time.

---

## Features

### Dashboard
- Summary stat cards: total devices, normal / critical / offline counts, and
  alert totals by status (active, acknowledged, resolved)
- Per-device gauge tiles showing the latest reading and status from the most
  recent tablet message
- Oxygen pressure step-chart with 15 min / 1 h / 24 h time window and
  per-device safe-low / safe-high reference lines
- Recent alerts list and recent activity feed

### Live Monitoring
- Full list of registered tablet devices with live status and gauge readings
- Per-device drawer: gauge readings, pressure trend chart, acknowledge / resolve
  actions, link to create or view an incident
- Status filter: All / Critical / Offline

### Alerts & Notifications
- Priority-ordered table (active first, then acknowledged, then resolved)
- Tabs synced to `?status=` query parameter for direct linking
- Alert detail drawer: timeline, readings before the alert, reasons from the
  tablet, confidence note when `confidence_pct <= 50`
- Acknowledge and Resolve with optional note; both are logged to the activity log
- Global bell icon in every page header with a count badge and dropdown of the
  six most recent active alerts
- Optional alert sound (Web Audio API beep) and browser notifications, both
  controllable from Settings

### Incident Management
- Create, update, and close incidents linked to a specific alert or device
- Status workflow: open → in_progress → closed (closing requires a resolution)
- Incident notes (append-only thread)
- Severity: Critical or Warning

### Analytics & Reports
- Configurable date range (defaults to last 7 days)
- Alert totals by type (PANEL_CRITICAL / TABLET_OFFLINE / UNREADABLE) and by
  device, with a per-day breakdown chart
- Device uptime percentage and readings count for the window
- Incident summary: open, in-progress, closed counts and average resolution time
- Oxygen pressure trend (kg/cm2 only, OXYGEN / Medical Air gauges, downsampled
  to 300 points per device)
- CSV export for alerts, incidents, and gauge readings (download via browser)

### Settings
- Profile: view name, role, email; change password
- Notification settings: toggle alert sound and browser notifications; test
  sound button
- System status: WebSocket connection, backend reachability, device summary,
  last data time, app version
- User management (Administrator only): list, create, edit role and active
  status for all users

### Shared / global
- Real-time updates via WebSocket push — the portal reloads data automatically
  on any `type: reading` or `type: alert` broadcast
- Toast notifications for new active alerts, with a "View" link to the alerts
  page (shown for 10 seconds)
- Light / dark mode toggle in the sidebar footer, persisted in localStorage
- Role-based access: Administrator, Monitoring Staff, Viewer
- 8-hour JWT session; stateless logout

---

## How it works

```
Tablet camera app
  → POST /api/readings  (JSON, no auth today)
    → Duplicate check (device_id + seq): ignore if already stored
    → Store tablet_messages + gauge_readings (skip VACUUM and mmHg gauges)
    → Update tablet_devices.last_seen_at and status
    → Alert state machine (integration/alerts.py):
        CRITICAL  → open a PANEL_CRITICAL alert if none is open
        NORMAL    → close any open PANEL_CRITICAL alert (cleared_at)
        late message (timestamp ≤ latest_message_at) → stored, alert skipped
    → Broadcast { type: "reading", device_id } over WebSocket
    → Portal clients reload summary / devices / alerts
```

Background watchdog (every 15 s):
- No message for **90 seconds** → open a `TABLET_OFFLINE` alert, set device
  status to OFFLINE
- Device status `UNREADABLE` for more than **120 seconds** → open an
  `UNREADABLE` alert
- When a live message arrives, both watchdog alert types are cleared
  automatically in the alert state machine

Additional rules enforced by the backend:
- Messages with `event == "test"` are discarded before any storage or alert
  logic runs
- A message whose `device_id + seq` already exists is acknowledged (HTTP 200)
  but not stored again
- Thresholds (`safe_low`, `safe_high`, `safe_critical`) come from the tablet
  payload and are stored as-is; the portal never recomputes them
- VACUUM gauges and gauges in mmHg are intentionally not stored or displayed
- Acknowledging an alert never changes the device's status field
- Late-arriving messages (timestamp older than the latest stored for that
  device) are stored for history but do not trigger alert changes

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend framework | Python 3.10+, FastAPI 0.111 |
| ASGI server | Uvicorn |
| Database driver | asyncpg (PostgreSQL) |
| Auth | JWT via python-jose, bcrypt passwords |
| WebSocket | FastAPI WebSocket (push-only) |
| Frontend framework | React 19, Vite 8 |
| Routing | React Router v7 |
| Styling | Tailwind CSS v4 |
| Charts | Recharts 3 |
| Icons | Lucide React |
| Database | PostgreSQL 14+ |

---

## Project structure

```
medical-gas-monitor/
├── backend/
│   ├── .env.example              # copy to .env, fill in DB_PASSWORD / JWT_SECRET
│   ├── requirements.txt
│   └── app/
│       ├── main.py               # FastAPI app, lifespan, router registration
│       ├── config.py             # Settings (pydantic-settings, reads .env)
│       ├── security.py           # JWT, bcrypt, auth dependencies
│       ├── ws_manager.py         # WebSocket connection manager
│       ├── db/
│       │   ├── database.py       # asyncpg pool, schema apply, seed users
│       │   └── schema.sql        # Idempotent DDL (all tables)
│       ├── models/
│       │   ├── schemas.py        # Pydantic models (auth, users)
│       │   └── tablet.py         # TabletMessage, GaugeReading models
│       ├── integration/
│       │   ├── adapter.py        # normalize() — raw JSON → TabletMessage
│       │   ├── alerts.py         # Alert state machine (CRITICAL/NORMAL/watchdog)
│       │   └── watchdog.py       # Background task: OFFLINE + UNREADABLE checks
│       └── routers/
│           ├── tablet.py         # POST /api/readings
│           ├── portal.py         # GET/PATCH /api/devices, /api/alerts, /api/activity, /api/summary
│           ├── auth.py           # POST /auth/login, GET /auth/me, POST /auth/change-password
│           ├── ws.py             # WebSocket /ws?token=
│           ├── users.py          # GET/POST/PATCH /api/users  (admin only)
│           ├── incidents.py      # /api/incidents CRUD + notes
│           └── analytics.py      # GET /api/analytics, GET /api/export/*.csv
├── docs/
│   ├── lead-spec.md              # Feature specification
│   ├── portal-guide.md           # Tablet message format and portal rules
│   └── sample.json               # Example tablet message
├── tools/
│   └── mock_tablet.py            # Test sender (see "Running the mock tablet")
└── frontend/
    ├── index.html
    ├── package.json
    └── src/
        ├── main.jsx              # Entry point, theme init
        ├── App.jsx               # Router + AuthProvider
        ├── PortalApp.jsx         # Shell, routes, global toasts, WS beep
        ├── config.js             # BASE_URL constant
        ├── api/
        │   ├── client.js         # fetch wrapper (Bearer token, 401 logout)
        │   ├── auth.js           # Login helper
        │   └── portal.js         # Typed wrappers for every backend endpoint
        ├── context/
        │   └── AuthContext.jsx   # Auth state, sessionStorage token
        ├── hooks/
        │   ├── useAuth.js
        │   ├── usePortalData.js  # summary, devices, alerts, activity + WS reload
        │   └── useWebSocket.js
        ├── pages/
        │   ├── Login.jsx
        │   ├── PortalDashboard.jsx
        │   ├── LiveMonitoring.jsx
        │   ├── PortalAlerts.jsx
        │   ├── Incidents.jsx
        │   ├── Analytics.jsx
        │   └── Settings.jsx
        └── components/
            ├── auth/             # LoginForm, LoginIllustration, DemoCredentials
            ├── cards/            # StatCard, SystemInfoCard
            ├── charts/           # Sparkline
            ├── layout/           # PortalShell, PortalSidebar, PortalTopBar
            ├── routing/          # ProtectedRoute
            └── ui/               # AlertToast, Drawer, Skeleton, StatusPill,
                                  # Toast, Toggle
```

---

## Prerequisites

| Tool | Minimum version |
|---|---|
| Python | 3.10 |
| Node.js | 18 |
| PostgreSQL | 14 |

Verify:

```powershell
python --version
node --version
psql --version
```

---

## Setup

### 1. Create the database

```sql
CREATE DATABASE medical_gas_db;
```

The backend applies the full schema and seeds demo users automatically on
first startup — no manual SQL needed.

### 2. Configure the backend

```powershell
copy medical-gas-monitor\backend\.env.example medical-gas-monitor\backend\.env
```

Open `.env` and fill in your values:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=medical_gas_db
DB_USER=postgres
DB_PASSWORD=your_password_here

JWT_SECRET=change-me-to-a-long-random-string
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_HOURS=8
```

### 3. Install backend dependencies

```powershell
cd medical-gas-monitor\backend
pip install -r requirements.txt
```

### 4. Install frontend dependencies

```powershell
cd medical-gas-monitor\frontend
npm install
```

---

## Run commands

Open separate PowerShell windows for each service. The backend must be
running before the frontend, and both must be running before using the mock
tablet.

### Backend

```powershell
cd medical-gas-monitor\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Expected startup output:

```
✅  Database connected, schema applied, seed checked.
   👤  Seeded user: dr.sharma (ADMINISTRATOR)
   👤  Seeded user: nurse.priya (MONITORING_STAFF)
   👤  Seeded user: nurse.anita (MONITORING_STAFF)
🔍  Offline/UNREADABLE watchdog started (interval: 15 s).
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Frontend

```powershell
cd medical-gas-monitor\frontend
npm run dev
```

| URL | Service |
|---|---|
| http://localhost:5173 | Portal (React / Vite) |
| http://localhost:8000/docs | FastAPI interactive API docs |
| http://localhost:8000 | Health check JSON |

### Mock tablet

The mock tablet (`tools/mock_tablet.py`) requires only the Python standard
library — no extra packages.

**Send a single NORMAL reading from device `tab-01`:**

```powershell
python medical-gas-monitor\tools\mock_tablet.py normal
```

**Send a CRITICAL reading from a custom device:**

```powershell
python medical-gas-monitor\tools\mock_tablet.py critical --device tab-02
```

**Run the full sequence (normal → critical → normal, 5 s apart):**

```powershell
python medical-gas-monitor\tools\mock_tablet.py sequence --device tab-01
```

**Run the multi-device demo (three devices, one goes critical then recovers):**

```powershell
python medical-gas-monitor\tools\mock_tablet.py multi
```

Available scenarios: `normal`, `critical`, `low`, `near_low`, `unreadable`,
`heartbeat`, `duplicate`, `out_of_order`, `sequence`, `multi`.

The `--url` flag overrides the default endpoint
(`http://localhost:8000/api/readings`):

```powershell
python medical-gas-monitor\tools\mock_tablet.py normal --url http://192.168.1.50:8000/api/readings
```

---

## Demo logins

Seeded automatically on first backend startup.

| Username | Password | Role |
|---|---|---|
| `dr.sharma` | `Doctor@123` | Administrator |
| `nurse.priya` | `Nurse@123` | Monitoring Staff |
| `nurse.anita` | `Nurse@123` | Monitoring Staff |

---

## Roles and permissions

| Action | Administrator | Monitoring Staff | Viewer |
|---|---|---|---|
| View dashboard, live monitoring, alerts, analytics | Yes | Yes | Yes |
| Acknowledge / resolve alerts | Yes | Yes | No |
| Create / update incidents, add notes | Yes | Yes | No |
| Change own password | Yes | Yes | Yes |
| List, create, edit users | Yes | No | No |
| Deactivate / change role of other users | Yes | No | No |

A Viewer receives HTTP 403 on any write operation. An Administrator cannot
deactivate their own account or demote themselves from the Administrator role.

---

## Connecting the real tablet

### 1. Start the backend bound to all interfaces

```powershell
cd medical-gas-monitor\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Find the laptop's LAN IP

```powershell
ipconfig
```

Look for the IPv4 address under your active network adapter
(e.g. `192.168.1.50`).

### 3. Open port 8000 in Windows Firewall

```powershell
netsh advfirewall firewall add rule name="OxygenFlowCheck-8000" protocol=TCP dir=in localport=8000 action=allow
```

### 4. Configure the tablet app

In the tablet app's Settings, set the portal endpoint to:

```
http://192.168.1.50:8000/api/readings
```

Then press "Send a test message". The app sends a message with `event: "test"`,
which the portal acknowledges with `{"status": "ignored"}` without storing any
data — this confirms connectivity.

### 5. Verify with curl or PowerShell

**PowerShell:**

```powershell
Invoke-RestMethod -Method POST -Uri "http://192.168.1.50:8000/api/readings" `
  -ContentType "application/json" `
  -Body '{
    "device_id": "tab-01",
    "timestamp": "2024-11-20T10:00:00+05:30",
    "seq": 1001,
    "event": "status_change",
    "alert_status": "NORMAL",
    "confidence_pct": 97,
    "gauges": [{
      "gauge_id": "tab-01-g1",
      "number": 1,
      "gas": "OXYGEN",
      "reading": 4.5,
      "unit": "kg/cm2",
      "status": "OK",
      "status_text": "within the safe range",
      "safe_low": 3.5,
      "safe_high": 5.5,
      "safe_critical": 3.0,
      "safe_buffer": 0.2,
      "confidence_pct": 96
    }],
    "lamps": ["green"],
    "reasons": [],
    "app_version": "0.1.0"
  }'
```

A successful response is `{"status": "ok", "message_id": <id>}`.

---

## API summary

All endpoints except `POST /api/readings`, `POST /auth/login`,
`GET /auth/logout`, and `GET /` require a `Bearer <token>` header.

### Tablet ingestion

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/readings` | Accept a tablet message (no auth) |

### Devices

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/devices` | List all tablet devices with latest gauges |
| `PATCH` | `/api/devices/{id}` | Update device name or location |
| `GET` | `/api/devices/{id}/readings` | Gauge reading history (`?gas=OXYGEN&minutes=60`) |

### Alerts

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/alerts` | List alerts (`?status=active\|acknowledged\|resolved\|all`) |
| `GET` | `/api/alerts/{id}` | Alert detail with pre-readings and linked incident |
| `POST` | `/api/alerts/{id}/acknowledge` | Acknowledge an alert (note optional) |
| `POST` | `/api/alerts/{id}/resolve` | Resolve an alert (note optional) |
| `GET` | `/api/summary` | Device and alert counts |
| `GET` | `/api/activity` | Last 15 activity log entries |

### Incidents

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/incidents` | List incidents (`?status=open\|in_progress\|closed\|all`) |
| `GET` | `/api/incidents/{id}` | Incident detail with notes and linked alert |
| `POST` | `/api/incidents` | Create incident |
| `PATCH` | `/api/incidents/{id}` | Update status, assigned_to, resolution, title, description |
| `POST` | `/api/incidents/{id}/notes` | Append a note |

### Analytics and export

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/analytics` | Aggregated stats (`?from=<ISO>&to=<ISO>`) |
| `GET` | `/api/export/alerts.csv` | Alert CSV download |
| `GET` | `/api/export/incidents.csv` | Incident CSV download |
| `GET` | `/api/export/readings.csv` | Gauge readings CSV download (kg/cm2 only) |

### Users and auth

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Username + password → JWT |
| `GET` | `/auth/me` | Current user info |
| `POST` | `/auth/logout` | Stateless logout (client drops token) |
| `POST` | `/auth/change-password` | Change own password |
| `GET` | `/api/users` | List all users (admin only) |
| `POST` | `/api/users` | Create user (admin only) |
| `PATCH` | `/api/users/{id}` | Update name, email, role, is_active (admin only) |

### WebSocket

| Path | Description |
|---|---|
| `/ws?token=<JWT>` | Push-only broadcast; server sends `{"type":"reading"\|"alert","device_id":"..."}` |

---

## Known limitations and future work

- **Camera feed placeholder.** The Live Monitoring page has a camera feed
  section that shows a placeholder until the tablet starts streaming a video
  or snapshot URL. This depends on data provided by the tablet app.

- **Threshold editing is disabled.** The Settings page shows safe thresholds
  as read-only. Editing them would require the tablet to fetch its thresholds
  from the portal on startup, which is not yet implemented.

- **No authentication on `POST /api/readings`.** The tablet ingestion endpoint
  accepts any POST request. Before deploying to a network accessible to
  untrusted clients, add an API key header check or restrict access by IP.

- **CSV export only.** The Analytics page exports CSV files. PDF and Excel
  formats are not supported.

- **Demo passwords and JWT secret must be changed.** The seeded passwords
  (`Doctor@123`, `Nurse@123`) and the default `JWT_SECRET` in `.env.example`
  are for local development only. Change them before connecting to any real
  network or real patient data.
