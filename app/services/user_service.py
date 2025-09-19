from __future__ import annotations

from typing import Optional

from app.core.db import db


async def get_user_profile(user_id: str):
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        return None

    links = await db.userinterest.find_many(
        where={"userId": user_id}, include={"interest": True}
    )
    interests = [
        li.interest for li in links if getattr(li, "interest", None) is not None
    ]
    custom = await db.custominterest.find_many(where={"userId": user_id})
    return user, interests, custom
