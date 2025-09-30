from datetime import datetime, timezone, timedelta
from http import HTTPStatus
from typing import Optional, Dict, TypedDict, cast
import os
import logging

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import RedirectResponse, JSONResponse
import httpx

from app.core.db import db
from app.services.google_oauth import oauth, GOOGLE_REDIRECT_URI
from app.services.queue import job_queue
from app.services.email_sync import schedule_periodic_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["auth"])


def _epoch_to_datetime(ts: Optional[float]) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except Exception:
        return None


@router.get(
    "/login",
    summary="Start Google OAuth login (redirect)",
    description=(
        "Initiates the Google OAuth 2.0 flow and redirects the user to Google. "
        "This endpoint uses GET to simplify browser navigation and linking. "
        "A POST variant is also provided for clients enforcing POST-only auth flows."
    ),
    operation_id="googleLoginGet",
)
async def google_login(request: Request):
    """Initiate Google OAuth redirect.

    Uses authlib's configured google client. Adds explicit offline access + consent to
    ensure a refresh token (first consent or when force prompt).
    """
    try:
        google = oauth.create_client("google")
        if google is None:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Google OAuth client not configured",
            )
        return await google.authorize_redirect(
            request,
            redirect_uri=GOOGLE_REDIRECT_URI,
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
    except Exception as exc:
        logger.exception("OAuth login init failed")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"OAuth init failed: {exc}",
        )


@router.get(
    "/callback",
    summary="Google OAuth callback",
    description=(
        "Handles the OAuth callback from Google, upserts the user and tokens, "
        "stores the session user_id, and schedules background email sync jobs."
    ),
    operation_id="googleCallback",
)
async def google_callback(request: Request):
    """Handle Google OAuth callback, upsert user + tokens, set session, trigger sync.

    Optimization goals:
    - Single interest presence check (avoid duplicate queries)
    - Unified token expiry derivation
    - Conditional background scheduling for any user with interests
    - Clear logging for observability
    """
    try:
        google = oauth.create_client("google")
        if google is None:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Google OAuth client not configured",
            )

        token = await google.authorize_access_token(request)
        logger.debug(
            "Received token keys: %s",
            list(token.keys()) if isinstance(token, dict) else type(token),
        )

        userinfo = None
        try:
            userinfo = await google.parse_id_token(request, token)
        except Exception:
            pass
        if not userinfo:
            resp = await google.get(
                "https://openidconnect.googleapis.com/v1/userinfo", token=token
            )
            userinfo = resp.json() if resp and resp.status_code == 200 else None
        if not userinfo:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Failed to retrieve Google user info",
            )

        google_sub = userinfo.get("sub")
        email = userinfo.get("email")
        name = userinfo.get("name") or userinfo.get("given_name")
        picture = userinfo.get("picture")
        if not google_sub or not email:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Google profile missing required fields",
            )

        user = await db.user.find_unique(where={"googleId": google_sub})
        is_new_user = user is None
        if is_new_user:
            user = await db.user.create(
                data={
                    "googleId": google_sub,
                    "email": email,
                    "name": name,
                    "picture": picture,
                }
            )
            if user is None:
                raise HTTPException(status_code=500, detail="Failed to create user")
            logger.info("Created new user id=%s email=%s", user.id, email)
        else:
            updated = await db.user.update(
                where={"id": user.id},
                data={
                    "email": email,
                    "name": name,
                    "picture": picture,
                },
            )
            user = updated or user
            logger.debug("Updated user id=%s", user.id)

        user_id = user.id

        expires_at = None
        if isinstance(token, dict):
            expires_at = _epoch_to_datetime(token.get("expires_at"))
            if not expires_at:
                try:
                    expires_in = int(token.get("expires_in") or 0)
                    if expires_in > 0:
                        expires_at = datetime.now(timezone.utc) + timedelta(
                            seconds=expires_in
                        )
                except Exception:
                    expires_at = None

        account = await db.googleaccount.find_unique(where={"userId": user_id})
        raw_refresh = token.get("refresh_token")
        refresh_token = (
            str(raw_refresh)
            if raw_refresh
            else (account.refreshToken if account and account.refreshToken else None)
        )
        base_access = str(token.get("access_token"))
        if not base_access:
            raise HTTPException(status_code=400, detail="Missing access token")

        token_type = (
            str(token.get("token_type"))
            if token.get("token_type")
            else (account.tokenType if account else None)
        )
        scope_val = (
            str(token.get("scope"))
            if token.get("scope")
            else (account.scope if account else None)
        )
        id_token_val = (
            str(token.get("id_token"))
            if token.get("id_token")
            else (account.idToken if account else None)
        )

        if account is None:
            await db.googleaccount.create(
                data={
                    "userId": user_id,
                    "accessToken": base_access,
                    "refreshToken": refresh_token,
                    "expiresAt": expires_at,
                    "tokenType": token_type,
                    "scope": scope_val,
                    "idToken": id_token_val,
                }
            )
            logger.debug("Created google account record for user=%s", user_id)
        else:
            await db.googleaccount.update(
                where={"id": account.id},
                data={
                    "accessToken": base_access,
                    "refreshToken": refresh_token,
                    "expiresAt": expires_at,
                    "tokenType": token_type,
                    "scope": scope_val,
                    "idToken": id_token_val,
                },
            )
            logger.debug("Updated google account token for user=%s", user_id)

        interests_sample, custom_sample = await _fetch_interest_presence(user_id)
        has_interests = bool(interests_sample or custom_sample)

        request.session["user_id"] = user_id
        logger.debug("Session user_id set for user=%s", user_id)

        if has_interests:
            try:
                await job_queue.put(
                    {"type": "sync_inbox_once", "user_id": user_id, "max_results": 10}
                )
                import asyncio

                interval = int(os.getenv("EMAIL_SYNC_INTERVAL_SECONDS", "3600"))
                asyncio.create_task(
                    schedule_periodic_sync(
                        user_id, interval_seconds=interval, max_results=10
                    )
                )
            except Exception:
                logger.exception("Failed to enqueue/schedule sync for user=%s", user_id)

        frontend = os.environ.get("FRONTEND_URL")
        if frontend:
            target_path = "/home" if has_interests else "/interests"
            return RedirectResponse(url=f"{frontend}{target_path}")

        return JSONResponse(
            {
                "message": "Google authentication successful",
                "user": {
                    "id": user_id,
                    "email": getattr(user, "email", None),
                    "name": getattr(user, "name", None),
                    "picture": getattr(user, "picture", None),
                    "has_interests": has_interests,
                    "is_new_user": is_new_user,
                },
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("OAuth callback failed")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"OAuth callback failed: {exc}",
        )


@router.post(
    "/logout",
    summary="Logout user (clear session)",
    description=(
        "Clears the server-side session (removing user_id). Optionally revokes the current "
        "Google access token if revoke=true is supplied. This endpoint is idempotent."
    ),
    operation_id="googleLogout",
)
async def google_logout(
    request: Request,
    revoke: bool = Query(
        False,
        description="If true, revoke the current Google OAuth token before logout",
    ),
):
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return JSONResponse({"message": "Already logged out"})

        if revoke:
            account = await db.googleaccount.find_first(where={"userId": user_id})
            if account and account.accessToken:
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.post(
                            "https://oauth2.googleapis.com/revoke",
                            data={"token": account.accessToken},
                            headers={
                                "Content-Type": "application/x-www-form-urlencoded"
                            },
                        )
                except Exception:
                    pass

        try:
            request.session.clear()
        except Exception:
            request.session["user_id"] = None

        return JSONResponse({"message": "Logged out"})
    except Exception as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Logout failed: {exc}",
        )


async def _fetch_interest_presence(user_id: str):
    """Fetch a minimal sample of user interests & custom interests (at most 1 each).

    Returns tuples (interests_sample, custom_sample) which are lists (len 0 or 1).
    Keeping this separate makes it easier to unit test and potentially extend.
    """
    interests = await db.interest.find_many(
        where={"users": {"some": {"userId": user_id}}}, take=1
    )
    custom = await db.custominterest.find_many(where={"userId": user_id}, take=1)
    return interests, custom
