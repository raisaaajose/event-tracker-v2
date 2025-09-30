from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, Optional

import httpx
import os

from app.services.google_api import get_user_google_token


CAL_BASE = "https://www.googleapis.com/calendar/v3"


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


async def create_event(
    user_id: str,
    summary: str,
    description: Optional[str],
    location: Optional[str],
    start: datetime,
    end: Optional[datetime],
) -> Dict[str, Any]:
    token = await get_user_google_token(user_id)
    headers = {
        "Authorization": f"Bearer {token['access_token']}",
        "Content-Type": "application/json",
    }
    body: Dict[str, Any] = {
        "summary": summary,
        "location": location,
        "description": description,
        "start": {"dateTime": _iso(start)},
        "end": {"dateTime": _iso(end or (start))},
    }
    try:
        reminder_minutes = int(os.getenv("CALENDAR_EVENT_REMINDER_MINUTES", "60"))
    except ValueError:
        reminder_minutes = 60
    if reminder_minutes > 0:
        body["reminders"] = {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": reminder_minutes},
            ],
        }
    else:
        body["reminders"] = {"useDefault": True}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{CAL_BASE}/calendars/primary/events", headers=headers, json=body
        )
        resp.raise_for_status()
        return resp.json()
