from __future__ import annotations

import logging
from sched import Event
from typing import List, Optional

import prisma

from app.core.db import db

logger = logging.getLogger(__name__)


async def list_events(
    user_id: str, limit: Optional[int] = None, offset: Optional[int] = None
):
    try:
        logger.debug(
            f"Fetching events for user {user_id} (limit={limit}, offset={offset})"
        )

        user_events = await db.userevent.find_many(
            where={"userId": user_id, "added": True},
            include={"event": True},
            take=limit,
            skip=offset,
            order={"createdAt": "desc"},
        )

        events = [ue.event for ue in user_events if ue.event is not None]
        logger.debug(f"Found {len(events)} events for user {user_id}")
        return events
    except Exception as e:
        logger.error(f"Error fetching events for user {user_id}: {e}")
        raise


async def delete_event(event_id: str, user_id: str) -> bool:
    """Delete an event by ID for a specific user. Returns True if deleted, False if not found or not owned."""
    try:
        logger.debug(f"Attempting to delete event {event_id} for user {user_id}")

        user_event = await db.userevent.find_first(
            where={"eventId": event_id, "userId": user_id}
        )
        if not user_event:
            logger.warning(f"Event {event_id} not found or not owned by user {user_id}")
            return False

        await db.userevent.delete(where={"id": user_event.id})
        logger.debug(f"Removed user association for event {event_id}")

        remaining_users = await db.userevent.count(where={"eventId": event_id})

        if remaining_users == 0:
            await db.event.delete(where={"id": event_id})
            logger.debug(f"Deleted event {event_id} as no other users have it")
        else:
            logger.debug(
                f"Event {event_id} kept as {remaining_users} other users still have it"
            )

        return True
    except Exception as e:
        logger.error(f"Error deleting event {event_id} for user {user_id}: {e}")
        return False
