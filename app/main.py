import os
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from .core.db import lifespan
from .api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    secret_key = os.getenv("SECRET_KEY", "dev-secret")
    app.add_middleware(SessionMiddleware, secret_key=secret_key)
    return app


app = create_app()
