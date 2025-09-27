from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from app.services import interest_service as svc
from app.model.api import (
    InterestOut,
    SetUserInterestsRequest,
    CustomInterestCreateRequest,
    CustomInterestOut,
    StatusResponse,
)
from app.core.auth import get_current_user_id


router = APIRouter(prefix="/interests", tags=["interests"])


@router.get(
    "/",
    response_model=list[InterestOut],
    summary="List all interests",
    description="Returns the catalog of available interests.",
)
async def get_interests():
    items = [i for i in (await svc.list_interests()) if i is not None]
    return [InterestOut(id=i.id, category=i.category, child=i.child) for i in items]


@router.put(
    "/me",
    response_model=StatusResponse,
    summary="Set my interests",
    description="Replace the current session user's interests with the provided list.",
)
async def set_my_interests(
    body: SetUserInterestsRequest, user_id: str = Depends(get_current_user_id)
):
    await svc.set_user_interests(user_id, body.interest_ids)
    return StatusResponse()


@router.get(
    "/me",
    response_model=list[InterestOut],
    summary="Get my interests",
    description="Returns the interests assigned to the current session user.",
)
async def get_my_interests(user_id: str = Depends(get_current_user_id)):
    items = [i for i in (await svc.list_user_interests(user_id)) if i is not None]
    return [InterestOut(id=i.id, category=i.category, child=i.child) for i in items]


@router.post(
    "/me/custom",
    response_model=CustomInterestOut,
    summary="Create my custom interest",
    description="Creates a custom interest for the current session user.",
)
async def create_my_custom_interest(
    body: CustomInterestCreateRequest, user_id: str = Depends(get_current_user_id)
):
    item = await svc.create_custom_interest(user_id, body.name)
    return CustomInterestOut(id=item.id, name=item.name)


@router.delete(
    "/me/custom/{custom_id}",
    response_model=StatusResponse,
    summary="Delete my custom interest",
    description="Deletes a custom interest association for the current user.",
)
async def delete_my_custom_interest(
    custom_id: str, user_id: str = Depends(get_current_user_id)
):
    await svc.delete_custom_interest(user_id, custom_id)
    return StatusResponse()


@router.post(
    "/sync",
    response_model=StatusResponse,
    summary="Trigger interest-based inbox sync",
    description=(
        "Manually enqueue an email sync job after updating interests. "
        "This avoids multiple automatic syncs while the user batches changes."
    ),
)
async def sync_after_interest_update(user_id: str = Depends(get_current_user_id)):
    try:
        from app.services.queue import job_queue

        # Enqueue a single immediate sync
        await job_queue.put(
            {"type": "sync_inbox_once", "user_id": user_id, "max_results": 10}
        )
        return StatusResponse()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to enqueue sync job: {str(e)}"
        )
