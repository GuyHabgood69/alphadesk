"""
JWT Authentication Middleware — protects all API endpoints.

Allows unauthenticated access only to:
  - /api/auth/login
  - /api/auth/logout
  - / (root health check)
  - /docs, /redoc, /openapi.json (Swagger)
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from routes.auth import extract_token, verify_token


# Paths that never require authentication
_PUBLIC_PATHS = frozenset({
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/auth/login",
    "/api/auth/logout",
})


class JwtAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests without a valid JWT (cookie or Bearer header)."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow public paths
        if path in _PUBLIC_PATHS:
            return await call_next(request)

        # Allow CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)

        # Extract token from cookie or Authorization header
        token = extract_token(request)

        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )

        payload = verify_token(token)
        if not payload:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        # Attach user info to request state
        request.state.user = payload["sub"]
        return await call_next(request)
