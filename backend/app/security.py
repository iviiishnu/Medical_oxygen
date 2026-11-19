"""
security.py
===========
JWT creation / verification, password hashing, and FastAPI dependency
functions that routers can use to protect endpoints.

Dependencies exported
---------------------
get_current_user    — decodes JWT, returns user dict; raises 401 on failure
require_role(role)  — factory that returns a dep raising 403 if role != required
require_any_role    — accepts any role; raises 401 if unauthenticated
require_write_role  — rejects VIEWER; ADMINISTRATOR and MONITORING_STAFF pass
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.db.database import get_pool

# ── Password hashing ──────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────
def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        hours=settings.access_token_expire_hours
    )
    payload["exp"] = expire
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises JWTError on failure."""
    return jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )


# ── OAuth2 scheme (used by Swagger UI) ───────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def _fetch_user_by_id(user_id: int) -> Optional[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id, u.name, u.username, u.role, u.ward_id,
                   u.email, u.is_active,
                   w.name AS ward_name
            FROM   users u
            LEFT   JOIN wards w ON w.id = u.ward_id
            WHERE  u.id = $1
            """,
            user_id,
        )
    return dict(row) if row else None


# ── Write-role guard (rejects VIEWER) ────────────────────────────────────────
def require_write_role():
    """Raises 403 for VIEWER; ADMINISTRATOR and MONITORING_STAFF pass through."""
    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] == "VIEWER":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Viewer role cannot perform this action",
            )
        return user
    return _dep


# ── Core dependency: decode token → user dict ────────────────────────────────
async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
) -> dict:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exc
    try:
        payload = decode_token(token)
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = await _fetch_user_by_id(int(user_id))
    if user is None:
        raise credentials_exc
    return user


# ── Role guard factory ────────────────────────────────────────────────────────
def require_role(role: str):
    """Returns a dependency that raises 403 if the user's role != role."""
    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role {role}",
            )
        return user
    return _dep


# ── Any-role dependency (just ensures authenticated) ─────────────────────────
async def require_any_role(user: dict = Depends(get_current_user)) -> dict:
    """Passes through as long as the JWT is valid (any role)."""
    return user


# ── WebSocket token helper (no Depends — called manually) ────────────────────
async def get_ws_user(token: str) -> Optional[dict]:
    """Validate a token from a WebSocket query param. Returns user or None."""
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return await _fetch_user_by_id(int(user_id))
    except JWTError:
        return None
