# Oxygen Flow Check — Setup & Run Guide

Condensed quick-start. See README.md for full documentation including API
reference, demo logins, roles, and connecting the real tablet.

---

## Prerequisites

| Tool | Minimum version | Download |
|---|---|---|
| Python | 3.10 | https://python.org/downloads |
| Node.js | 18 | https://nodejs.org |
| PostgreSQL | 14 | https://postgresql.org/download |

```powershell
python --version
node --version
psql --version
```

---

## Step 1 — Database

```sql
CREATE DATABASE medical_gas_db;
```

The backend creates all tables and seeds demo users on first startup.

---

## Step 2 — Backend

```powershell
cd medical-gas-monitor\backend
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set `DB_PASSWORD` and `JWT_SECRET` at minimum:

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

---

## Step 3 — Frontend

```powershell
cd medical-gas-monitor\frontend
npm install
```

---

## Running

### Terminal 1 — Backend (port 8000)

```powershell
cd medical-gas-monitor\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2 — Frontend (port 5173)

```powershell
cd medical-gas-monitor\frontend
npm run dev
```

| URL | Service |
|---|---|
| http://localhost:5173 | Portal |
| http://localhost:8000/docs | API docs |

---

## Demo logins

| Username | Password | Role |
|---|---|---|
| `dr.sharma` | `Doctor@123` | Administrator |
| `nurse.priya` | `Nurse@123` | Monitoring Staff |
| `nurse.anita` | `Nurse@123` | Monitoring Staff |

---

## Sending test data

```powershell
python medical-gas-monitor\tools\mock_tablet.py normal
python medical-gas-monitor\tools\mock_tablet.py critical --device tab-02
python medical-gas-monitor\tools\mock_tablet.py multi
```

See README.md → "Run commands" for all scenarios and the real-tablet
connection instructions.
