"""
routers/users.py
================
User management API — Administrator only.

GET   /api/users          — list all users
POST  /api/users           — create a new user
PATCH  /api/users/{id}     — update name, email, role, is_active

All write actions are logged to activity_log.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from app.db.database import get_pool
from app.security import get_current_user, hash_password, require_role
from app.models.schemas import UserManageOut, UserCreate, UserPatch

router = APIRouter(prefix="/api/users", tags=["users"])

# Administrator-only dependency
_admin = Depends(require_role("ADMINISTRATOR"))

VALID_ROLES = {"ADMINISTRATOR", "MONITORING_STAFF", "VIEWER"}


@router.get("", response_model=list[UserManageOut])
async def list_users(user: dict = _admin):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, username, name, email, role, is_active, created_at
            FROM   users
            ORDER  BY created_at ASC
            """
        )
    return [dict(r) for r in rows]


@router.post("", response_model=UserManageOut, status_code=201)
async def create_user(body: UserCreate, user: dict = _admin):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of {sorted(VALID_ROLES)}")

    pool = get_pool()
    async with pool.acquire() as conn:
        # Reject duplicate username
        existing = await conn.fetchval(
            "SELECT id FROM users WHERE username = $1", body.username
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )

        new_id = await conn.fetchval(
            """
            INSERT INTO users (name, username, password_hash, role, email)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            body.name, body.username, hash_password(body.password), body.role, body.email,
        )

        row = await conn.fetchrow(
            "SELECT id, username, name, email, role, is_active, created_at FROM users WHERE id = $1",
            new_id,
        )

        await conn.execute(
            """
            INSERT INTO activity_log (event_type, actor, detail)
            VALUES ($1, $2, $3)
            """,
            "user_created", user["username"],
            f"Created user '{body.username}' ({body.role})",
        )

    return dict(row)


@router.patch("/{user_id}", response_model=UserManageOut)
async def update_user(user_id: int, body: UserPatch, user: dict = _admin):
    if body.role is not None and body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of {sorted(VALID_ROLES)}")

    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, username, name, email, role, is_active, created_at FROM users WHERE id = $1",
            user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        # An admin cannot deactivate or demote themselves
        if user_id == user["id"]:
            if body.is_active is False:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You cannot deactivate your own account",
                )
            if body.role is not None and body.role != "ADMINISTRATOR":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You cannot demote yourself from Administrator",
                )

        await conn.execute(
            """
            UPDATE users
            SET    name      = COALESCE($1, name),
                   email     = COALESCE($2, email),
                   role      = COALESCE($3, role),
                   is_active = COALESCE($4, is_active)
            WHERE  id = $5
            """,
            body.name, body.email, body.role, body.is_active, user_id,
        )

        updated = await conn.fetchrow(
            "SELECT id, username, name, email, role, is_active, created_at FROM users WHERE id = $1",
            user_id,
        )

        # Build a readable detail string for the activity log
        changes = []
        if body.name is not None and body.name != row["name"]:
            changes.append(f"name→{body.name}")
        if body.email is not None and body.email != row["email"]:
            changes.append(f"email→{body.email or '(cleared)'}")
        if body.role is not None and body.role != row["role"]:
            changes.append(f"role→{body.role}")
        if body.is_active is not None and body.is_active != row["is_active"]:
            changes.append(f"active→{body.is_active}")
        detail = f"Updated user '{row['username']}': {', '.join(changes)}" if changes else f"Touched user '{row['username']}'"

        await conn.execute(
            """
            INSERT INTO activity_log (event_type, actor, detail)
            VALUES ($1, $2, $3)
            """,
            "user_updated", user["username"], detail,
        )

    return dict(updated)
