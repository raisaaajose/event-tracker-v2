from fastapi import FastAPI
from .core.db import lifespan
from .api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
