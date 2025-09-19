from __future__ import annotations

from fastapi import APIRouter, Query

from app.services import event_service as svc
from app.model.api import EventOut


router = APIRouter(prefix="/events", tags=["events"])


@router.get(
    "/",
    response_model=list[EventOut],
    summary="List events",
    description="Returns events with optional pagination via limit and offset.",
)
async def get_events(
    limit: int | None = Query(
        default=None, ge=1, le=200, description="Max items to return"
    ),
    offset: int | None = Query(
        default=None, ge=0, description="Items to skip from start"
    ),
):
    items = await svc.list_events(limit=limit, offset=offset)
    return [
        EventOut(
            id=e.id,
            title=e.title,
            description=e.description,
            location=e.location,
            platform=e.platform,
            link=e.link,
            startTime=e.startTime,
            endTime=e.endTime,
            source=e.source,
            sourceId=e.sourceId,
        )
        for e in items
        if e is not None
    ]
