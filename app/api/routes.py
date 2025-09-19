from fastapi import APIRouter
from .auth import router as auth_router
from .interests import router as interests_router
from .events import router as events_router
from .users import router as users_router

router = APIRouter()


@router.get(
    "/",
    summary="Service info",
    description="Basic info endpoint for the backend service.",
)
async def root():
    return {"message": "Event Tracker Backend running"}


@router.get(
    "/ping", summary="Liveness ping", description="Simple liveness probe endpoint."
)
async def ping():
    return {"status": "ok"}


@router.get(
    "/health",
    summary="Health check",
    description="Health and readiness status for the service.",
)
async def health_check():
    return {"status": "healthy", "message": "Service is running"}


router.include_router(auth_router)
router.include_router(interests_router)
router.include_router(events_router)
router.include_router(users_router)
