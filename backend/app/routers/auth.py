"""
routers/auth.py
===============
POST /auth/login                — verify credentials + optional role, return JWT
GET  /auth/me                   — return current user info
POST /auth/logout               — stateless logout (client drops token)
POST /auth/change-password      — change own password (requires current pw)
"""

from fastapi import APIRouter, HTTPException, status, Depends

from app.db.database import get_pool
from app.models.schemas import LoginRequest, TokenResponse, UserOut, ChangePasswordRequest
from app.security import (
    verify_password,
    hash_password,
    create_access_token,
    get_current_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id, u.name, u.username, u.password_hash,
                   u.role, u.ward_id, u.is_active,
                   w.name AS ward_name
            FROM   users u
            LEFT   JOIN wards w ON w.id = u.ward_id
            WHERE  u.username = $1
            """,
            body.username,
        )

    # Unknown user or wrong password → 401
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not verify_password(body.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Reject deactivated accounts with a clear message
    if not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated. Contact an administrator.",
        )

    # Role check: only performed when the client sends a role
    if body.role is not None:
        requested = body.role.upper()
        if requested not in ("ADMINISTRATOR", "MONITORING_STAFF", "VIEWER"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        if row["role"] != requested:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

    token = create_access_token({"sub": str(row["id"])})

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut(
            id=row["id"],
            name=row["name"],
            username=row["username"],
            role=row["role"],
            ward_id=row["ward_id"],
            ward_name=row["ward_name"],
            email=row.get("email"),
        ),
    )


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    # Filter to only fields that UserOut expects
    return UserOut(
        id=user["id"],
        name=user["name"],
        username=user["username"],
        role=user["role"],
        ward_id=user.get("ward_id"),
        ward_name=user.get("ward_name"),
        email=user.get("email"),
    )


@router.post("/logout", status_code=200)
async def logout():
    """
    Stateless JWT logout — the client simply drops the token.
    Endpoint exists so front-ends can call it uniformly.
    """
    return {"detail": "Logged out successfully"}


# ══════════════════════════════════════════════════════════════════════════════
# POST /auth/change-password
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/change-password", status_code=200)
async def change_password(body: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, password_hash FROM users WHERE id = $1",
            user["id"],
        )
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        if not verify_password(body.current_password, row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        new_hash = hash_password(body.new_password)
        await conn.execute(
            "UPDATE users SET password_hash = $1 WHERE id = $2",
            new_hash, user["id"],
        )

        # Activity log
        await conn.execute(
            """
            INSERT INTO activity_log (event_type, actor, detail)
            VALUES ($1, $2, $3)
            """,
            "password_changed", user["username"], "User changed their password",
        )

    return {"detail": "Password changed successfully"}
