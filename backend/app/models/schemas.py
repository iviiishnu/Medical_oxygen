"""
models/schemas.py
=================
Pydantic request/response models for the portal API.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str
    password: str
    role:     Optional[str] = None   # optional; if omitted the stored role is used


class UserOut(BaseModel):
    id:        int
    name:      str
    username:  str
    role:      str
    ward_id:   Optional[int]
    ward_name: Optional[str]
    email:     Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         UserOut


# ══════════════════════════════════════════════════════════════════════════════
# USER MANAGEMENT (Settings page)
# ══════════════════════════════════════════════════════════════════════════════

class UserManageOut(BaseModel):
    id:         int
    username:   str
    name:       str
    email:      Optional[str] = None
    role:       str
    is_active:  bool
    created_at: datetime


class UserCreate(BaseModel):
    username: str   = Field(..., min_length=1, max_length=60)
    name:     str   = Field(..., min_length=1, max_length=100)
    email:    Optional[str] = None
    password: str   = Field(..., min_length=1)
    role:     str   = Field(..., description="ADMINISTRATOR | MONITORING_STAFF | VIEWER")


class UserPatch(BaseModel):
    name:      Optional[str]  = None
    email:     Optional[str]  = None
    role:      Optional[str]  = None
    is_active: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password:     str = Field(..., min_length=8)
