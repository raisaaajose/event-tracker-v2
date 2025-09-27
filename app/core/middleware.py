from __future__ import annotations

from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
import logging


class RequireSessionUserMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, exempt_paths: Iterable[str] | None = None):
        super().__init__(app)
        self.exempt_paths = set(exempt_paths or [])

    async def dispatch(self, request: Request, call_next):
        path: str = request.url.path or "/"

        if request.method in {"OPTIONS", "HEAD"}:
            return await call_next(request)

        for prefix in self.exempt_paths:
            if path.startswith(prefix):
                return await call_next(request)

        user_id = None
        if hasattr(request, "session"):
            try:
                user_id = request.session.get("user_id")
            except Exception as e:
                logging.debug(f"Session retrieval failed: {e}")
                user_id = None

        if user_id:
            request.state.user_id = str(user_id)
            return await call_next(request)

        logging.debug(
            "Auth middleware rejecting request: path=%s method=%s session_keys=%s",
            path,
            request.method,
            (
                list(getattr(request, "session", {}).keys())
                if hasattr(request, "session")
                else None
            ),
        )
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
