from datetime import datetime, timezone, timedelta
from http import HTTPStatus
from typing import Optional, Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse

from app.core.db import db
from app.services.google_oauth import oauth, GOOGLE_REDIRECT_URI

router = APIRouter(prefix="/auth/google", tags=["auth"])


def _epoch_to_datetime(ts: Optional[float]) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except Exception:
        return None


@router.get("/login")
async def google_login(request: Request):
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
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"OAuth init failed: {exc}",
        )


@router.get("/callback")
async def google_callback(request: Request):
    try:
        google = oauth.create_client("google")
        if google is None:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Google OAuth client not configured",
            )
        token = await google.authorize_access_token(request)

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

        user: Any = await db.user.find_unique(where={"googleId": google_sub})
        if user is None:
            user = await db.user.create(
                data={
                    "googleId": google_sub,
                    "email": email,
                    "name": name,
                    "picture": picture,
                }
            )
        else:
            user = await db.user.update(
                where={"id": user.id},
                data={
                    "email": email,
                    "name": name,
                    "picture": picture,
                },
            )

        expires_at = None
        if isinstance(token, dict):
            expires_at = _epoch_to_datetime(token.get("expires_at"))
            if not expires_at:
                try:
                    expires_in_val = token.get("expires_in", 0) or 0
                    expires_in = int(expires_in_val)
                    if expires_in > 0:
                        expires_at = datetime.now(timezone.utc) + timedelta(
                            seconds=expires_in
                        )
                except Exception:
                    expires_at = None

        account = await db.googleaccount.find_unique(where={"userId": user.id})
        if account is None:
            await db.googleaccount.create(
                data={
                    "userId": user.id,
                    "accessToken": str(token.get("access_token")),
                    "refreshToken": str(token.get("refresh_token")),
                    "expiresAt": expires_at,
                    "tokenType": token.get("token_type"),
                    "scope": token.get("scope"),
                    "idToken": token.get("id_token"),
                }
            )
        else:
            await db.googleaccount.update(
                where={"id": account.id},
                data={
                    "accessToken": str(token.get("access_token")),
                    "refreshToken": str(token.get("refresh_token"))
                    or account.refreshToken,
                    "expiresAt": expires_at,
                    "tokenType": str(token.get("token_type")),
                    "scope": str(token.get("scope")) or account.scope,
                    "idToken": str(token.get("id_token")) or account.idToken,
                },
            )

        import os

        frontend = os.environ.get("FRONTEND_URL")
        if frontend:
            return RedirectResponse(url=f"{frontend}?login=success&user_id={user.id}")

        return JSONResponse(
            {
                "message": "Google authentication successful",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "picture": user.picture,
                },
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"OAuth callback failed: {exc}",
        )
