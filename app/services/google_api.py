from datetime import datetime, timezone, timedelta
from typing import Optional
import os

import httpx

from app.core.db import db


class GoogleAuthError(Exception):
    pass


async def get_user_google_token(user_id: str) -> dict:
    account = await db.googleaccount.find_unique(where={"userId": user_id})
    if not account:
        raise GoogleAuthError("Google account not connected")

    token = {
        "access_token": account.accessToken,
        "refresh_token": account.refreshToken,
        "expires_at": account.expiresAt.timestamp() if account.expiresAt else None,
        "token_type": account.tokenType,
        "scope": account.scope,
        "id_token": account.idToken,
    }
    if (
        account.expiresAt
        and account.expiresAt <= datetime.now(timezone.utc)
        and account.refreshToken
    ):
        data = {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": account.refreshToken,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://oauth2.googleapis.com/token", data=data)
            resp.raise_for_status()
            new_token = resp.json()
        expires_in = new_token.get("expires_in")
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            if expires_in
            else None
        )
        await db.googleaccount.update(
            where={"id": account.id},
            data={
                "accessToken": new_token.get("access_token"),
                "expiresAt": expires_at,
                "tokenType": new_token.get("token_type") or account.tokenType,
                "scope": new_token.get("scope") or account.scope,
                "idToken": new_token.get("id_token") or account.idToken,
            },
        )
        token.update(
            {
                "access_token": new_token.get("access_token"),
                "expires_at": expires_at.timestamp() if expires_at else None,
            }
        )

    return token
