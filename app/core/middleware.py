from __future__ import annotations

from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse


class RequireSessionUserMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, exempt_paths: Iterable[str] | None = None):
        super().__init__(app)
        self.exempt_paths = set(exempt_paths or [])

    async def dispatch(self, request: Request, call_next):
        path: str = request.url.path or "/"

        for prefix in self.exempt_paths:
            if path.startswith(prefix):
                return await call_next(request)

        scope_session = (
            request.scope.get("session") if isinstance(request.scope, dict) else None
        )
        user_id = (
            scope_session.get("user_id") if isinstance(scope_session, dict) else None
        )
        if user_id:
            request.state.user_id = str(user_id)
            return await call_next(request)

        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
