import os
from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlparse
from .core.db import lifespan
from .api.routes import router
from .core.middleware import RequireSessionUserMiddleware


tags_metadata = [
    {
        "name": "auth",
        "description": "Google OAuth 2.0 login and callback endpoints.",
    },
    {
        "name": "interests",
        "description": "List interests and manage user/custom interests.",
    },
    {
        "name": "events",
        "description": "List extracted events created from Gmail via LLM pipeline.",
    },
    {
        "name": "users",
        "description": "User profile endpoints including interests and custom interests.",
    },
]


def create_app() -> FastAPI:
    load_dotenv(override=False)
    app = FastAPI(
        title="Event Tracker API",
        version="0.1.0",
        description=(
            "Backend API for Event Tracker. Includes Google OAuth, Gmail ingestion, "
            "LLM-based event extraction, Google Calendar creation, and interest/profile endpoints."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=tags_metadata,
        lifespan=lifespan,
    )
    app.include_router(router)
    secret_key = os.getenv("SECRET_KEY", "dev-secret")

    env = os.getenv("ENVIRONMENT", "development").lower()
    session_cookie = os.getenv("SESSION_COOKIE", "session")
    session_domain = os.getenv("SESSION_DOMAIN")
    same_site = os.getenv("SESSION_SAMESITE", "lax").lower()
    if same_site not in {"lax", "strict", "none"}:
        same_site = "lax"
    max_age_days = int(os.getenv("SESSION_MAX_AGE_DAYS", "7"))
    max_age = max(1, max_age_days) * 24 * 60 * 60
    https_only = (
        True
        if same_site == "none"
        else os.getenv("SESSION_SECURE", "false").lower() == "true"
        or env == "production"
    )

    from typing import Literal

    samesite_literal: Literal["lax", "strict", "none"] = "lax"
    if same_site == "none":
        samesite_literal = "none"
    elif same_site == "strict":
        samesite_literal = "strict"

    frontend_url = os.getenv("FRONTEND_URL")
    frontend_origin = None
    if frontend_url:
        try:
            parsed = urlparse(frontend_url)
            if parsed.scheme and parsed.netloc:
                frontend_origin = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            frontend_origin = None

    allow_origins = (
        [frontend_origin]
        if frontend_origin
        else [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
        session_cookie=session_cookie,
        max_age=max_age,
        same_site=samesite_literal,
        https_only=https_only,
        domain=session_domain,
        path="/",
    )
    app.add_middleware(
        RequireSessionUserMiddleware,
        exempt_paths=(
            "/",
            "/auth/",
            "/health",
            "/ping",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


app = create_app()
