from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.db import db
from app.services.google_api import get_user_google_token
from app.model.llm import (
    EmailHeader,
    EmailMessage,
    LLMExtractionInput,
    LLMExtractionOutput,
    ProposedEvent,
)
from app.services.google_calendar import create_event
from app.services.llm_client import extract_events


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
            params={"format": "full"},
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


def _extract_body(payload: Dict[str, Any]) -> Optional[str]:
    """
    Extract the email body text from Gmail API payload.
    Handles both plain text and HTML, prioritizing plain text.
    """
    import base64

    def get_text_from_part(part: Dict[str, Any]) -> Optional[str]:
        mime_type = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")

        if data:
            try:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            except Exception:
                return None

        if "parts" in part:
            for nested_part in part["parts"]:
                text = get_text_from_part(nested_part)
                if text and (mime_type == "text/plain" or not mime_type):
                    return text

        return None

    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                text = get_text_from_part(part)
                if text:
                    return text

        for part in payload["parts"]:
            text = get_text_from_part(part)
            if text:
                return text

    body = payload.get("body", {})
    data = body.get("data")
    if data:
        try:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        except Exception:
            pass

    return None


async def process_messages(user_id: str, messages: List[Dict[str, Any]]) -> int:
    """
    Process Gmail messages and queue them for LLM extraction.
    Only processes messages that haven't been seen before.
    """
    if not messages:
        return 0

    cs = await db.calendarsync.find_unique(where={"userId": user_id})
    last_processed_msg_id = cs.lastProcessedMessageId if cs else None

    email_models: List[EmailMessage] = []
    latest_internal: Optional[datetime] = None
    latest_msg_id: Optional[str] = None
    found_last_processed = last_processed_msg_id is None

    for m in messages:
        msg_id = m.get("id")
        if not msg_id:
            continue

        if not found_last_processed:
            if msg_id == last_processed_msg_id:
                found_last_processed = True
            continue

        detail = await get_message_detail(user_id, msg_id)
        payload = detail.get("payload", {})
        headers_raw = payload.get("headers", [])
        headers = [
            EmailHeader(name=h.get("name", ""), value=h.get("value", ""))
            for h in headers_raw
        ]
        subject = next((h.value for h in headers if h.name.lower() == "subject"), None)
        sender = next((h.value for h in headers if h.name.lower() == "from"), None)
        to_addr = next((h.value for h in headers if h.name.lower() == "to"), None)
        date_hdr = next((h.value for h in headers if h.name.lower() == "date"), None)
        internal_date = _parse_internal_date(detail.get("internalDate"))
        body = _extract_body(payload)

        if internal_date and (
            latest_internal is None or internal_date > latest_internal
        ):
            latest_internal = internal_date
            latest_msg_id = msg_id

        email_models.append(
            EmailMessage(
                id=msg_id,
                subject=subject,
                sender=sender,
                to=to_addr,
                date=date_hdr,
                body=body,
                internal_date=internal_date,
                headers=headers,
            )
        )

    if not email_models:
        return 0

    interests = await db.interest.find_many(
        where={"users": {"some": {"userId": user_id}}}
    )
    interest_names = [f"{i.category}:{i.child}" for i in interests]
    custom = await db.custominterest.find_many(where={"userId": user_id})
    custom_names = [c.name for c in custom]

    llm_input = LLMExtractionInput(
        user_id=user_id,
        interests=interest_names,
        custom_interests=custom_names,
        emails=email_models,
    )

    from app.services.queue import job_queue

    await job_queue.put(
        {
            "type": "process_llm_and_calendar",
            "user_id": user_id,
            "payload": llm_input.model_dump(),
            "latest_internal": latest_internal.isoformat() if latest_internal else None,
            "latest_msg_id": latest_msg_id,
        }
    )

    return len(email_models)


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
    elif kind == "process_llm_and_calendar":
        user_id = job["user_id"]
        payload = job.get("payload") or {}
        latest_internal_iso = job.get("latest_internal")
        latest_msg_id = job.get("latest_msg_id")
        latest_internal = None
        if isinstance(latest_internal_iso, str):
            try:
                latest_internal = datetime.fromisoformat(latest_internal_iso)
            except Exception:
                latest_internal = None

        llm_input = LLMExtractionInput.model_validate(payload)
        llm_output = await extract_events(llm_input)

        for ev in llm_output.events:
            if ev.source_message_id:
                existing = await db.event.find_first(
                    where={"sourceId": ev.source_message_id, "source": "gmail"}
                )
                if existing:
                    continue

            try:
                cal_ev = await create_event(
                    user_id=user_id,
                    summary=ev.title,
                    description=ev.description,
                    location=ev.location,
                    start=ev.start_time,
                    end=ev.end_time,
                )
                await db.event.create(
                    data={
                        "title": ev.title,
                        "description": ev.description,
                        "location": ev.location,
                        "platform": "google-calendar",
                        "link": cal_ev.get("htmlLink"),
                        "startTime": ev.start_time,
                        "endTime": ev.end_time,
                        "source": "gmail",
                        "sourceId": ev.source_message_id,
                        "users": {"create": [{"userId": user_id, "added": True}]},
                    }
                )
            except Exception as e:
                print(f"Error creating event from email {ev.source_message_id}: {e}")
                continue

        if latest_internal is not None or latest_msg_id is not None:
            await db.calendarsync.upsert(
                where={"userId": user_id},
                data={
                    "create": {
                        "userId": user_id,
                        "lastProcessedDate": latest_internal,
                        "lastProcessedMessageId": latest_msg_id,
                    },
                    "update": {
                        "lastProcessedDate": latest_internal,
                        "lastProcessedMessageId": latest_msg_id,
                    },
                },
            )


async def schedule_periodic_sync(
    user_id: str, interval_seconds: int = 3600, max_results: int = 10
) -> None:
    from app.services.queue import job_queue

    while True:
        await job_queue.put(
            {"type": "sync_inbox_once", "user_id": user_id, "max_results": max_results}
        )
        await asyncio.sleep(interval_seconds)
