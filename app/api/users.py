from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from app.services import user_service
from app.model.api import UserProfileOut, InterestOut, CustomInterestOut
from app.core.auth import get_current_user_id


router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me/profile",
    response_model=UserProfileOut,
    summary="Get my profile",
    description="Returns the profile for the current session user.",
)
async def get_my_profile(user_id: str = Depends(get_current_user_id)):
    result = await user_service.get_user_profile(user_id)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    user, interests, custom = result
    return UserProfileOut(
        id=user.id,
        email=user.email,
        name=user.name,
        picture=user.picture,
        interests=[
            InterestOut(id=i.id, category=i.category, child=i.child)
            for i in interests
            if i is not None
        ],
        custom_interests=[
            CustomInterestOut(id=c.id, name=c.name) for c in custom if c is not None
        ],
    )
