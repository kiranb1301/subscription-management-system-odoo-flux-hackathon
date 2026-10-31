from fastapi import APIRouter

from app.api.routes import root
from app.api.v1.router import api_router as v1_router
from app.settings import settings

api_router = APIRouter()

api_router.include_router(root.router, tags=["Root"])
api_router.include_router(v1_router, prefix=settings.API_V1_PREFIX)
