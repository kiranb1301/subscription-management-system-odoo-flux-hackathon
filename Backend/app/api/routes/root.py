from fastapi import APIRouter

from app.schemas.root import RootResponse
from app.services import root_service

router = APIRouter()


@router.get("/", response_model=RootResponse)
def root():
    return root_service.get_root_info()