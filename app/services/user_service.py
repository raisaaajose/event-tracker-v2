from __future__ import annotations

import logging
from typing import Optional

from app.core.db import db

logger = logging.getLogger(__name__)


async def get_user_profile(user_id: str):
    try:
        logger.debug(f"Fetching profile for user: {user_id}")

        user = await db.user.find_unique(where={"id": user_id})
        if not user:
            logger.warning(f"User not found: {user_id}")
            return None

        links = await db.userinterest.find_many(
            where={"userId": user_id}, include={"interest": True}
        )
        interests = [
            li.interest for li in links if getattr(li, "interest", None) is not None
        ]

        custom = await db.custominterest.find_many(where={"userId": user_id})

        logger.debug(
            f"Found profile for user {user_id}: {len(interests)} interests, {len(custom)} custom interests"
        )
        return user, interests, custom
    except Exception as e:
        logger.error(f"Error fetching user profile for {user_id}: {e}")
        raise
