from __future__ import annotations

import logging
from typing import List

from app.core.db import db

logger = logging.getLogger(__name__)


async def list_interests():
    try:
        logger.debug("Fetching all interests")
        interests = await db.interest.find_many()
        logger.debug(f"Found {len(interests)} total interests")
        return interests
    except Exception as e:
        logger.error(f"Error fetching all interests: {e}")
        raise


async def set_user_interests(user_id: str, interest_ids: List[str]):
    try:
        logger.debug(f"Setting interests for user {user_id}: {interest_ids}")

        if interest_ids:
            existing_interests = await db.interest.find_many(
                where={"id": {"in": interest_ids}}
            )
            existing_ids = {interest.id for interest in existing_interests}
            invalid_ids = [iid for iid in interest_ids if iid not in existing_ids]
            if invalid_ids:
                raise ValueError(f"Invalid interest IDs: {invalid_ids}")

        await db.userinterest.delete_many(where={"userId": user_id})

        if interest_ids:
            for iid in interest_ids:
                try:
                    await db.userinterest.create(
                        data={"userId": user_id, "interestId": iid}
                    )
                except Exception as e:
                    if "unique" not in str(e).lower():
                        logger.error(
                            f"Error creating user interest {user_id}-{iid}: {e}"
                        )
                        raise

        logger.debug(
            f"Successfully set {len(interest_ids) if interest_ids else 0} interests for user {user_id}"
        )
    except Exception as e:
        logger.error(f"Error setting user interests for user {user_id}: {e}")
        raise


async def list_user_interests(user_id: str):
    try:
        logger.debug(f"Fetching interests for user: {user_id}")
        links = await db.userinterest.find_many(
            where={"userId": user_id}, include={"interest": True}
        )
        interests = [
            li.interest for li in links if getattr(li, "interest", None) is not None
        ]
        logger.debug(f"Found {len(interests)} interests for user: {user_id}")
        return interests
    except Exception as e:
        logger.error(f"Error fetching user interests for user {user_id}: {e}")
        raise


async def create_custom_interest(user_id: str, name: str):
    try:
        logger.debug(f"Creating custom interest '{name}' for user {user_id}")

        if not name or not name.strip():
            raise ValueError("Custom interest name cannot be empty")

        name = name.strip()

        existing = await db.custominterest.find_first(
            where={"userId": user_id, "name": name}
        )
        if existing:
            raise ValueError(f"Custom interest '{name}' already exists for this user")

        custom_interest = await db.custominterest.create(
            data={"userId": user_id, "name": name}
        )

        logger.debug(
            f"Successfully created custom interest '{name}' for user {user_id}"
        )
        return custom_interest
    except Exception as e:
        logger.error(f"Error creating custom interest '{name}' for user {user_id}: {e}")
        raise


async def delete_custom_interest(user_id: str, custom_interest_id: str):
    try:
        logger.debug(
            f"Deleting custom interest {custom_interest_id} for user {user_id}"
        )

        existing = await db.custominterest.find_first(
            where={"id": custom_interest_id, "userId": user_id}
        )
        if not existing:
            raise ValueError(f"Custom interest not found or does not belong to user")

        await db.custominterest.delete(where={"id": custom_interest_id})

        logger.debug(
            f"Successfully deleted custom interest {custom_interest_id} for user {user_id}"
        )
    except Exception as e:
        logger.error(
            f"Error deleting custom interest {custom_interest_id} for user {user_id}: {e}"
        )
        raise


async def list_custom_interests(user_id: str):
    return await db.custominterest.find_many(where={"userId": user_id})
