from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import PageParams, require_staff
from app.db.session import get_db
from app.models import User
from app.schemas.common import Page
from app.schemas.invoice import BillingJobResponse, BillingRunRequest
from app.services import invoice_service as service

router = APIRouter()


@router.post("/run", response_model=BillingJobResponse)
def run_billing(
    payload: BillingRunRequest | None = None,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    run_date = payload.run_date if payload else None
    return service.run_billing(db, staff_user, run_date)


@router.get("/jobs", response_model=Page[BillingJobResponse])
def list_jobs(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    items, total = service.list_jobs(db, params.offset, params.page_size)
    return Page(
        items=[BillingJobResponse.model_validate(j) for j in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )