from __future__ import annotations

from typing import List, Optional

from app.core.db import db


async def list_events(limit: Optional[int] = None, offset: Optional[int] = None):
    events = await db.event.find_many()
    if offset:
        events = events[offset:]
    if limit:
        events = events[:limit]
    return events
