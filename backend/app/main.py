"""
Medical Gas Monitoring — FastAPI backend v2
===========================================
Startup: connects to PostgreSQL, applies schema + seed, starts HTTP + WebSocket,
and launches the offline/UNREADABLE watchdog background task.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db, close_db
from app.routers import ws, auth
from app.routers import tablet
from app.routers import portal
from app.routers import users as users_router
from app.routers import incidents as incidents_router
from app.routers import analytics as analytics_router
from app.integration.watchdog import watchdog_loop


# ── Background tasks ──────────────────────────────────────────────────────────
_watchdog_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _watchdog_task
    await init_db()
    # Apply idempotent incident schema
    from app.routers.incidents import ensure_schema as ensure_incidents_schema
    await ensure_incidents_schema()
    _watchdog_task = asyncio.create_task(watchdog_loop())
    print("🔍  Offline/UNREADABLE watchdog started (interval: 15 s).")
    yield
    if _watchdog_task:
        _watchdog_task.cancel()
    await close_db()


app = FastAPI(
    title="Medical Gas Monitoring API v2",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — allow all origins for now (tighten in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(ws.router)
app.include_router(tablet.router)             # POST /api/readings — tablet ingestion
app.include_router(portal.router)             # Portal API — summary, devices, alerts, activity
app.include_router(users_router.router)       # User management — admin only
app.include_router(incidents_router.router)   # Incident management
app.include_router(analytics_router.router)   # Analytics & CSV exports


@app.get("/", tags=["health"])
async def health():
    return {
        "status": "ok",
        "service": "medical-gas-monitor-v2",
        "features": [
            "JWT auth",
            "role-based access (ADMINISTRATOR/MONITORING_STAFF/VIEWER)",
            "tablet ingestion (POST /api/readings)",
            "offline watchdog (90 s TABLET_OFFLINE, 120 s UNREADABLE)",
            "portal API (summary, devices, alerts, activity)",
            "WebSocket push (readings + alert changes)",
            "incident management",
            "analytics & CSV exports",
        ],
    }
