from fastapi import FastAPI

from app.api.router import api_router
from app.core.exceptions import register_exception_handlers
from app.core.middleware import register_middleware
from app.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_TITLE,
        version=settings.APP_VERSION,
        description=settings.APP_DESCRIPTION,
    )

    register_middleware(app)
    register_exception_handlers(app)
    app.include_router(api_router)

    return app