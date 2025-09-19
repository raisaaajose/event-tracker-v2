from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status


def get_current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        user_id = (
            request.session.get("user_id") if hasattr(request, "session") else None
        )
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    return str(user_id)
