from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.db import db
from app.services.google_api import get_user_google_token


GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


async def fetch_latest_messages(
    user_id: str, max_results: int = 10, page_token: Optional[str] = None, q: str = ""
) -> Dict[str, Any]:
    token = await get_user_google_token(user_id)
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    params: Dict[str, Any] = {"maxResults": max_results}
    if q:
        params["q"] = q
    if page_token:
        params["pageToken"] = page_token

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{GMAIL_API_BASE}/messages", headers=headers, params=params
        )
        resp.raise_for_status()
        return resp.json()


async def get_message_detail(user_id: str, message_id: str) -> Dict[str, Any]:
    token = await get_user_google_token(user_id)
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{GMAIL_API_BASE}/messages/{message_id}",
            headers=headers,
            params={
                "format": "metadata",
                "metadataHeaders": ["subject", "from", "to", "date"],
            },
        )
        resp.raise_for_status()
        return resp.json()


def _parse_internal_date(ms_str: Optional[str]) -> Optional[datetime]:
    try:
        if ms_str is None:
            return None
        return datetime.fromtimestamp(int(ms_str) / 1000.0, tz=timezone.utc)
    except Exception:
        return None


async def process_messages(user_id: str, messages: List[Dict[str, Any]]) -> int:
    if not messages:
        return 0

    created = 0
    latest_internal: Optional[datetime] = None
    for m in messages:
        msg_id = m.get("id")
        if not msg_id:
            continue

        existing = await db.event.find_first(
            where={"sourceId": msg_id, "source": "gmail"}
        )
        if existing:
            continue

        detail = await get_message_detail(user_id, msg_id)
        subject = ""
        headers = detail.get("payload", {}).get("headers", [])
        for h in headers:
            if h.get("name", "").lower() == "subject":
                subject = h.get("value", "")
                break
        internal_date = _parse_internal_date(detail.get("internalDate"))
        if internal_date and (
            latest_internal is None or internal_date > latest_internal
        ):
            latest_internal = internal_date

        await db.event.create(
            data={
                "title": subject or "(no subject)",
                "description": None,
                "location": None,
                "platform": "gmail",
                "link": None,
                "startTime": internal_date or datetime.now(timezone.utc),
                "endTime": None,
                "source": "gmail",
                "sourceId": msg_id,
                "users": {"create": [{"userId": user_id, "added": True}]},
            }
        )
        created += 1

    if latest_internal is not None:
        await db.calendarsync.upsert(
            where={"userId": user_id},
            data={
                "create": {"userId": user_id, "lastProcessedDate": latest_internal},
                "update": {"lastProcessedDate": latest_internal},
            },
        )

    return created


async def sync_user_inbox_once(user_id: str, max_results: int = 10) -> int:
    cs = await db.calendarsync.find_unique(where={"userId": user_id})
    q = ""
    if cs and cs.lastProcessedDate:
        try:
            q_date = cs.lastProcessedDate.astimezone(timezone.utc).strftime("%Y/%m/%d")
            q = f"after:{q_date}"
        except Exception:
            q = ""
    data = await fetch_latest_messages(user_id, max_results=max_results, q=q)
    msgs = data.get("messages", [])
    return await process_messages(user_id, msgs)


async def handle_job(job: Dict[str, Any]) -> None:
    kind = job.get("type")
    if kind == "sync_inbox_once":
        user_id = job["user_id"]
        max_results = int(job.get("max_results", 10))
        await sync_user_inbox_once(user_id, max_results=max_results)


async def schedule_periodic_sync(
    user_id: str, interval_seconds: int = 3600, max_results: int = 10
) -> None:
    from app.services.queue import job_queue

    while True:
        await job_queue.put(
            {"type": "sync_inbox_once", "user_id": user_id, "max_results": max_results}
        )
        await asyncio.sleep(interval_seconds)
