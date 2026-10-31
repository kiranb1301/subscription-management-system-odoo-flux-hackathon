from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_user, require_staff
from app.core.permissions import is_staff
from app.db.session import get_db
from app.models import User
from app.models.enums import PaymentMethod, PaymentStatus
from app.schemas.common import Page
from app.schemas.payment import PaymentCreate, PaymentResponse
from app.schemas.subscription import ReasonRequest
from app.services import payment_service as service

router = APIRouter()


@router.get("", response_model=Page[PaymentResponse])
def list_payments(
    status: PaymentStatus | None = Query(None),
    method: PaymentMethod | None = Query(None),
    customer_id: int | None = Query(None, description="Staff only; ignored for customers"),
    invoice_id: int | None = Query(None, description="Payments allocated to this invoice"),
    search: str | None = Query(None, description="Match on payment reference"),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = service.list_payments(
        db, current_user, params.offset, params.page_size,
        status, method, customer_id, invoice_id, search,
    )
    return Page(
        items=service.to_responses(items, is_staff(current_user)),
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("", response_model=PaymentResponse, status_code=201)
def record_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    payment = service.record_payment(db, staff_user, payload)
    return service.to_responses([payment], True)[0]


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payment = service.get_payment_for_user(db, current_user, payment_id)
    return service.to_responses([payment], is_staff(current_user))[0]


@router.post("/{payment_id}/refund", response_model=PaymentResponse)
def refund_payment(
    payment_id: int,
    payload: ReasonRequest | None = None,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    reason = (payload.reason if payload else None) or None
    payment = service.refund_payment(db, staff_user, payment_id, reason)
    return service.to_responses([payment], True)[0]