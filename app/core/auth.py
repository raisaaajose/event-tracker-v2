from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status


def get_current_user_id(request: Request) -> str:
    import logging

    logger = logging.getLogger(__name__)

    user_id = getattr(request.state, "user_id", None)
    logger.debug(f"user_id from request.state: {user_id}")

    if not user_id and hasattr(request, "session"):
        try:
            user_id = request.session.get("user_id")
            logger.debug(f"user_id from session: {user_id}")
        except Exception as e:
            logger.warning(f"Session access failed: {e}")
            user_id = None

    if not user_id:
        logger.warning("No user_id found in request state or session")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in first.",
        )

    logger.debug(f"Returning user_id: {user_id}")
    return str(user_id)
