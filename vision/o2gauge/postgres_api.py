"""PostgreSQL-backed account and monitoring API (no external identity provider)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, g, jsonify, request

from . import postgres_store as store

api = Blueprint("postgres_api", __name__)
SESSION_TTL_SECONDS = 12 * 60 * 60


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _secret() -> bytes:
    secret = os.getenv("AUTH_SECRET", "").encode("utf-8")
    if len(secret) < 32:
        raise store.StoreUnavailable("Set AUTH_SECRET to a random value of at least 32 characters on the backend.")
    return secret


def hash_password(password: str) -> str:
    if len(password) < 10 or len(password) > 1024:
        raise ValueError("Password must be between 10 and 1024 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return f"scrypt${_b64(salt)}${_b64(digest)}"


def _verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, salt_part, digest_part = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_part + "=" * (-len(salt_part) % 4))
        expected = base64.urlsafe_b64decode(digest_part + "=" * (-len(digest_part) % 4))
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _issue_token(user: dict[str, Any]) -> str:
    payload = {"uid": user["uid"], "iat": int(time.time()), "exp": int(time.time()) + SESSION_TTL_SECONDS}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_identity(token: str) -> dict[str, Any]:
    if not token:
        raise PermissionError("Sign in to use the monitoring backend.")
    try:
        body, signature = token.split(".", 1)
        expected = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("Expired token")
        uid = str(payload.get("uid") or "")
    except store.StoreUnavailable:
        raise
    except Exception as exc:
        raise PermissionError("The session is invalid or expired. Sign in again.") from exc
    if not uid:
        raise PermissionError("The session is invalid. Sign in again.")
    with store.connection() as conn:
        user = conn.execute(
            "SELECT uid,email,display_name,role,on_duty FROM staff WHERE uid=%s AND is_active=TRUE",
            (uid,),
        ).fetchone()
    if not user or user["role"] not in ("staff", "admin"):
        raise PermissionError("This PostgreSQL account is inactive or does not have staff access.")
    return {**user, "sub": user["uid"], "name": user["display_name"]}


def _identity_from_request() -> dict[str, Any]:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer":
        token = ""
    return verify_identity(token.strip())


def _authenticated(fn: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(fn)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            g.identity = _identity_from_request()
            return fn(*args, **kwargs)
        except PermissionError as exc:
            return jsonify(error=str(exc)), 401
        except store.StoreUnavailable as exc:
            return jsonify(error=str(exc)), 503
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except LookupError as exc:
            return jsonify(error=str(exc)), 404
    return wrapped


@api.after_app_request
def add_cors_headers(response: Any) -> Any:
    origin = request.headers.get("Origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
    return response


@api.route("/api/v1/<path:_path>", methods=["OPTIONS"])
def preflight(_path: str) -> Any:
    return "", 204


@api.post("/api/v1/auth/login")
def login() -> Any:
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error="Send email and password as a JSON object."), 400
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    if not email or not password:
        return jsonify(error="Enter your staff email and password."), 400
    try:
        with store.connection() as conn:
            user = conn.execute(
                "SELECT uid,email,display_name,role,on_duty,password_hash FROM staff WHERE lower(email)=lower(%s) AND is_active=TRUE",
                (email,),
            ).fetchone()
        if not user or user["role"] not in ("staff", "admin") or not _verify_password(password, user["password_hash"]):
            return jsonify(error="Email or password is incorrect."), 401
        return jsonify(token=_issue_token(user), user={
            "uid": user["uid"], "email": user["email"], "displayName": user["display_name"],
            "role": user["role"], "onDuty": user["on_duty"],
        })
    except store.StoreUnavailable as exc:
        return jsonify(error=str(exc)), 503


@api.get("/api/v1/me")
@_authenticated
def me() -> Any:
    row = g.identity
    return jsonify(uid=row["uid"], email=row["email"], displayName=row["display_name"], role=row["role"], onDuty=row["on_duty"])


@api.route("/api/v1/devices", methods=["GET", "POST"])
@_authenticated
def devices() -> Any:
    if request.method == "GET":
        return jsonify(store.list_devices(g.identity))
    store.register_device(g.identity, request.get_json(silent=True) or {})
    return jsonify(ok=True), 201


@api.get("/api/v1/alerts")
@_authenticated
def alerts() -> Any:
    return jsonify(store.list_alerts(g.identity))


@api.get("/api/v1/devices/<device_id>/readings")
@_authenticated
def readings(device_id: str) -> Any:
    return jsonify(store.get_history(g.identity, device_id))


@api.post("/api/v1/alerts/<alert_id>/acknowledge")
@_authenticated
def acknowledge_alert(alert_id: str) -> Any:
    store.acknowledge(g.identity, alert_id, request.get_json(silent=True) or {})
    return jsonify(ok=True)
