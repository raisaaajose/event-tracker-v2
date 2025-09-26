from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from http import HTTPStatus

from app.services import event_service as svc
from app.model.api import EventOut, StatusResponse


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


@router.delete(
    "/{event_id}",
    response_model=StatusResponse,
    summary="Delete event",
    description="Deletes an event by ID. Returns 404 if the event doesn't exist.",
)
async def delete_event(event_id: str):
    success = await svc.delete_event(event_id)
    if not success:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Event with ID {event_id} not found",
        )
    return StatusResponse()
