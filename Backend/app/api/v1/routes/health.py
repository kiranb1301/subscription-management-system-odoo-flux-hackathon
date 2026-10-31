from fastapi import APIRouter

from app.schemas.health import HealthResponse
from app.services import health_service

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check():
    return health_service.get_health_status()