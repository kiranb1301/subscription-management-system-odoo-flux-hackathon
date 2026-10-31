from app.schemas.health import HealthResponse
from app.settings import settings


def get_health_status() -> HealthResponse:
    return HealthResponse(status="healthy", application=settings.APP_NAME)