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


@router.options("/me")
async def options_my_interests():
    """Handle CORS preflight requests for /me endpoint."""
    return {"message": "OK"}


@router.options("/me/custom")
async def options_my_custom_interests():
    """Handle CORS preflight requests for /me/custom endpoint."""
    return {"message": "OK"}


@router.options("/sync")
async def options_sync():
    """Handle CORS preflight requests for /sync endpoint."""
    return {"message": "OK"}


@router.get(
    "/",
    response_model=list[InterestOut],
    summary="List all interests",
    description="Returns the catalog of available interests.",
)
async def get_interests():
    try:
        items = [i for i in (await svc.list_interests()) if i is not None]
        return [InterestOut(id=i.id, category=i.category, child=i.child) for i in items]
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch interests: {str(e)}"
        )


@router.put(
    "/me",
    response_model=StatusResponse,
    summary="Set my interests",
    description="Replace the current session user's interests with the provided list.",
)
async def set_my_interests(
    body: SetUserInterestsRequest, user_id: str = Depends(get_current_user_id)
):
    import logging

    logger = logging.getLogger(__name__)

    try:
        logger.info(f"Setting interests for user {user_id}: {body.interest_ids}")
        await svc.set_user_interests(user_id, body.interest_ids)
        logger.info(f"Successfully set interests for user {user_id}")
        return StatusResponse()
    except ValueError as e:
        logger.warning(f"Validation error setting interests for user {user_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            f"Unexpected error setting interests for user {user_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to update interests: {str(e)}"
        )


@router.get(
    "/me",
    response_model=list[InterestOut],
    summary="Get my interests",
    description="Returns the interests assigned to the current session user.",
)
async def get_my_interests(user_id: str = Depends(get_current_user_id)):
    try:
        items = [i for i in (await svc.list_user_interests(user_id)) if i is not None]
        return [InterestOut(id=i.id, category=i.category, child=i.child) for i in items]
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get interests: {str(e)}"
        )


@router.post(
    "/me/custom",
    response_model=CustomInterestOut,
    summary="Create my custom interest",
    description="Creates a custom interest for the current session user.",
)
async def create_my_custom_interest(
    body: CustomInterestCreateRequest, user_id: str = Depends(get_current_user_id)
):
    try:
        item = await svc.create_custom_interest(user_id, body.name)
        return CustomInterestOut(id=item.id, name=item.name)
    except ValueError as e:
        if "already exists" in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if "unique constraint" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(
                status_code=409, detail=f"Custom interest '{body.name}' already exists"
            )
        raise HTTPException(
            status_code=500, detail=f"Failed to create custom interest: {str(e)}"
        )


@router.delete(
    "/me/custom/{custom_id}",
    response_model=StatusResponse,
    summary="Delete my custom interest",
    description="Deletes a custom interest association for the current user.",
)
async def delete_my_custom_interest(
    custom_id: str, user_id: str = Depends(get_current_user_id)
):
    try:
        await svc.delete_custom_interest(user_id, custom_id)
        return StatusResponse()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete custom interest: {str(e)}"
        )


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
    from app.services.queue import job_queue

    # Enqueue a single immediate sync
    await job_queue.put(
        {"type": "sync_inbox_once", "user_id": user_id, "max_results": 10}
    )
    return StatusResponse()
