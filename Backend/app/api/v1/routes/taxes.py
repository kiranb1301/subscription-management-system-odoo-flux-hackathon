from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, require_admin, require_staff
from app.db.session import get_db
from app.models import User
from app.schemas.common import Page
from app.schemas.tax import TaxCreate, TaxResponse, TaxUpdate
from app.services import tax_service

router = APIRouter()


@router.get("", response_model=Page[TaxResponse])
def list_taxes(
    is_active: bool | None = Query(None),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    items, total = tax_service.list_taxes(db, params.offset, params.page_size, is_active)
    return Page(
        items=[TaxResponse.model_validate(t) for t in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{tax_id}", response_model=TaxResponse)
def get_tax(tax_id: int, db: Session = Depends(get_db), _: User = Depends(require_staff)):
    return tax_service.get_tax(db, tax_id)


@router.post("", response_model=TaxResponse, status_code=201)
def create_tax(
    payload: TaxCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    return tax_service.create_tax(db, payload)


@router.put("/{tax_id}", response_model=TaxResponse)
def update_tax(
    tax_id: int,
    payload: TaxUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return tax_service.update_tax(db, tax_id, payload)


@router.delete("/{tax_id}", status_code=204)
def deactivate_tax(
    tax_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    tax_service.deactivate_tax(db, tax_id)