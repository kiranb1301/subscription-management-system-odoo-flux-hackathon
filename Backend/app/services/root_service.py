from app.schemas.root import RootResponse
from app.settings import settings


def get_root_info() -> RootResponse:
    return RootResponse(
        application=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs="/docs",
        health=f"{settings.API_V1_PREFIX}/health",
    )