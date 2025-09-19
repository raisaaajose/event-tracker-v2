from __future__ import annotations

from typing import List

from app.core.db import db


async def list_interests():
    return await db.interest.find_many()


async def set_user_interests(user_id: str, interest_ids: List[str]):
    await db.userinterest.delete_many(where={"userId": user_id})
    if interest_ids:
        for iid in interest_ids:
            await db.userinterest.create(data={"userId": user_id, "interestId": iid})


async def list_user_interests(user_id: str):
    links = await db.userinterest.find_many(
        where={"userId": user_id}, include={"interest": True}
    )
    return [li.interest for li in links if getattr(li, "interest", None) is not None]


async def create_custom_interest(user_id: str, name: str):
    return await db.custominterest.create(data={"userId": user_id, "name": name})


async def delete_custom_interest(user_id: str, custom_interest_id: str):
    await db.custominterest.delete_many(
        where={"id": custom_interest_id, "userId": user_id}
    )


async def list_custom_interests(user_id: str):
    return await db.custominterest.find_many(where={"userId": user_id})
