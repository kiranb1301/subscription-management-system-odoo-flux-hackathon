from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_user, require_staff
from app.core.permissions import is_staff
from app.db.session import get_db
from app.models import User
from app.models.enums import QuotationStatus
from app.schemas.common import Page
from app.schemas.quotation import QuotationCreate, QuotationResponse, QuotationUpdate
from app.services import quotation_service as service

router = APIRouter()


@router.get("", response_model=Page[QuotationResponse])
def list_quotations(
    status: QuotationStatus | None = Query(None),
    customer_id: int | None = Query(None, description="Staff only; ignored for customers"),
    search: str | None = Query(None, description="Match on quotation number"),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    staff = is_staff(current_user)
    items, total = service.list_quotations(
        db, current_user, params.offset, params.page_size, status, customer_id, search
    )
    return Page(
        items=[QuotationResponse.from_quotation(q, staff) for q in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{quotation_id}", response_model=QuotationResponse)
def get_quotation(
    quotation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quotation = service.get_quotation_for_user(db, current_user, quotation_id)
    return QuotationResponse.from_quotation(quotation, is_staff(current_user))


@router.post("", response_model=QuotationResponse, status_code=201)
def create_quotation(
    payload: QuotationCreate,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    return QuotationResponse.from_quotation(
        service.create_quotation(db, payload, staff_user), True
    )


@router.put("/{quotation_id}", response_model=QuotationResponse)
def update_quotation(
    quotation_id: int,
    payload: QuotationUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    return QuotationResponse.from_quotation(
        service.update_quotation(db, quotation_id, payload), True
    )


@router.delete("/{quotation_id}", status_code=204)
def delete_quotation(
    quotation_id: int, db: Session = Depends(get_db), _: User = Depends(require_staff)
):
    service.delete_quotation(db, quotation_id)


@router.post("/{quotation_id}/send", response_model=QuotationResponse)
def send_quotation(
    quotation_id: int, db: Session = Depends(get_db), _: User = Depends(require_staff)
):
    return QuotationResponse.from_quotation(service.send_quotation(db, quotation_id), True)


@router.post("/{quotation_id}/confirm", response_model=QuotationResponse)
def confirm_quotation(
    quotation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quotation = service.confirm_quotation(db, current_user, quotation_id)
    return QuotationResponse.from_quotation(quotation, is_staff(current_user))


@router.post("/{quotation_id}/reject", response_model=QuotationResponse)
def reject_quotation(
    quotation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quotation = service.reject_quotation(db, current_user, quotation_id)
    return QuotationResponse.from_quotation(quotation, is_staff(current_user))