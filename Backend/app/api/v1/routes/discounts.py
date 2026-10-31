from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, require_admin, require_staff
from app.db.session import get_db
from app.models import User
from app.schemas.common import Page
from app.schemas.discount import DiscountCreate, DiscountResponse, DiscountUpdate
from app.services import discount_service as service

router = APIRouter()


@router.get("", response_model=Page[DiscountResponse])
def list_discounts(
    search: str | None = Query(None, description="Match on code or name"),
    is_active: bool | None = Query(None),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    items, total = service.list_discounts(db, params.offset, params.page_size, search, is_active)
    return Page(
        items=[DiscountResponse.from_discount(d) for d in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{discount_id}", response_model=DiscountResponse)
def get_discount(
    discount_id: int, db: Session = Depends(get_db), _: User = Depends(require_staff)
):
    return DiscountResponse.from_discount(service.get_discount(db, discount_id))


@router.post("", response_model=DiscountResponse, status_code=201)
def create_discount(
    payload: DiscountCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    return DiscountResponse.from_discount(service.create_discount(db, payload))


@router.put("/{discount_id}", response_model=DiscountResponse)
def update_discount(
    discount_id: int,
    payload: DiscountUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return DiscountResponse.from_discount(service.update_discount(db, discount_id, payload))


@router.delete("/{discount_id}", status_code=204)
def deactivate_discount(
    discount_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    service.deactivate_discount(db, discount_id)