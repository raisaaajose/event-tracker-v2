from __future__ import annotations

from sched import Event
from typing import List, Optional

import prisma

from app.core.db import db


async def list_events(limit: Optional[int] = None, offset: Optional[int] = None):
    events: List[prisma.models.Event] = await db.event.find_many()
    if offset:
        events = events[offset:]
    if limit:
        events = events[:limit]
    return events
