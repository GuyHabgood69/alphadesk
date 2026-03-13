"""
Authentication routes — login / logout / session check.
"""

from __future__ import annotations

import hashlib
import secrets
import time

import jwt
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── JWT helpers ────────────────────────────────────────────────────────

_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_SECONDS = 60 * 60 * 24  # 24 hours

def _get_secret() -> str:
    """Return the JWT signing secret, auto-generating one if not configured."""
    if settings.jwt_secret:
        return settings.jwt_secret
    # Deterministic fallback derived from the dashboard password
    return hashlib.sha256(
        f"alphadesk-jwt-{settings.dashboard_password}".encode()
    ).hexdigest()


def _create_token(username: str) -> str:
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + _JWT_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, _get_secret(), algorithm=_JWT_ALGORITHM)


def verify_token(token: str) -> dict | None:
    """Decode and verify a JWT. Returns the payload dict or None."""
    try:
        return jwt.decode(token, _get_secret(), algorithms=[_JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def extract_token(request: Request) -> str | None:
    """Extract JWT from cookie or Authorization header."""
    token = request.cookies.get("alphadesk_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    return token or None


# ── Request / Response models ──────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


# ── Routes ─────────────────────────────────────────────────────────────

@router.post("/login")
async def login(body: LoginRequest, response: Response):
    if body.username != settings.dashboard_user or body.password != settings.dashboard_password:
        return Response(
            content='{"detail":"Invalid username or password"}',
            status_code=401,
            media_type="application/json",
        )

    token = _create_token(body.username)

    # Set httpOnly cookie (secure in production, lax for dev)
    response.set_cookie(
        key="alphadesk_token",
        value=token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        max_age=_JWT_EXPIRY_SECONDS,
        path="/",
    )

    return {"ok": True, "user": body.username}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("alphadesk_token", path="/")
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    token = extract_token(request)

    if not token:
        return Response(
            content='{"detail":"Not authenticated"}',
            status_code=401,
            media_type="application/json",
        )

    payload = verify_token(token)
    if not payload:
        return Response(
            content='{"detail":"Invalid or expired token"}',
            status_code=401,
            media_type="application/json",
        )

    return {"user": payload["sub"]}
