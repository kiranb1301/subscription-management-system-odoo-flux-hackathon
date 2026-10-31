from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_user, require_staff
from app.core.permissions import is_staff
from app.db.session import get_db
from app.models import User
from app.models.enums import InvoiceStatus
from app.schemas.common import Page
from app.schemas.invoice import (
    ApplyDiscountRequest,
    GenerateInvoiceRequest,
    InvoiceHistoryResponse,
    InvoiceResponse,
    InvoiceUpdate,
)
from app.schemas.subscription import ReasonRequest
from app.services import invoice_service as service
from app.services.invoice_pdf import render_invoice_pdf

router = APIRouter()


@router.get("", response_model=Page[InvoiceResponse])
def list_invoices(
    status: InvoiceStatus | None = Query(None),
    customer_id: int | None = Query(None, description="Staff only; ignored for customers"),
    subscription_id: int | None = Query(None),
    search: str | None = Query(None, description="Match on invoice number"),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    staff = is_staff(current_user)
    items, total = service.list_invoices(
        db, current_user, params.offset, params.page_size, status, customer_id, subscription_id, search
    )
    return Page(
        items=service.to_responses(db, items, staff),
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/generate", response_model=InvoiceResponse, status_code=201)
def generate_invoice(
    payload: GenerateInvoiceRequest,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    inv = service.generate_for_subscription(db, staff_user, payload.subscription_id)
    return service.to_responses(db, [inv], True)[0]


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = service.get_invoice_for_user(db, current_user, invoice_id)
    return service.to_responses(db, [inv], is_staff(current_user))[0]


@router.get("/{invoice_id}/history", response_model=list[InvoiceHistoryResponse])
def get_history(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    staff = is_staff(current_user)
    rows = service.list_history(db, current_user, invoice_id)
    return [
        InvoiceHistoryResponse(
            from_status=h.from_status,
            to_status=h.to_status,
            reason=h.reason,
            changed_at=h.changed_at,
            changed_by=h.changed_by if staff else None,
        )
        for h in rows
    ]


@router.get("/{invoice_id}/pdf")
def download_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = service.get_invoice_for_user(db, current_user, invoice_id)
    pdf = render_invoice_pdf(inv)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{inv.invoice_number}.pdf"'},
    )


@router.put("/{invoice_id}", response_model=InvoiceResponse)
def update_invoice(
    invoice_id: int,
    payload: InvoiceUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    inv = service.update_invoice(db, invoice_id, payload)
    return service.to_responses(db, [inv], True)[0]


@router.post("/{invoice_id}/apply-discount", response_model=InvoiceResponse)
def apply_discount(
    invoice_id: int,
    payload: ApplyDiscountRequest,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    inv = service.apply_discount(db, staff_user, invoice_id, payload.code)
    return service.to_responses(db, [inv], True)[0]


@router.post("/{invoice_id}/remove-discount", response_model=InvoiceResponse)
def remove_discount(
    invoice_id: int,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    inv = service.remove_discount(db, staff_user, invoice_id)
    return service.to_responses(db, [inv], True)[0]


@router.post("/{invoice_id}/confirm", response_model=InvoiceResponse)
def confirm_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    inv = service.confirm_invoice(db, staff_user, invoice_id)
    return service.to_responses(db, [inv], True)[0]


@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
def cancel_invoice(
    invoice_id: int,
    payload: ReasonRequest | None = None,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    reason = (payload.reason if payload else None) or None
    inv = service.cancel_invoice(db, staff_user, invoice_id, reason)
    return service.to_responses(db, [inv], True)[0]