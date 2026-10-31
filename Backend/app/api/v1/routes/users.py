from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, require_admin
from app.db.session import get_db
from app.models import User
from app.schemas.common import Page
from app.schemas.user import StaffCreateRequest, UserActiveUpdate, UserAdminResponse
from app.services import user_service

router = APIRouter()


@router.post("", response_model=UserAdminResponse, status_code=201)
def create_staff_account(
    payload: StaffCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return UserAdminResponse.from_user(user_service.create_staff(db, payload))


@router.get("", response_model=Page[UserAdminResponse])
def list_users(
    role: str | None = Query(None),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    items, total = user_service.list_users(db, params.offset, params.page_size, role)
    return Page(
        items=[UserAdminResponse.from_user(u) for u in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.patch("/{user_id}/active", response_model=UserAdminResponse)
def set_user_active(
    user_id: int,
    payload: UserActiveUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = user_service.set_active(db, admin, user_id, payload.is_active)
    return UserAdminResponse.from_user(user)