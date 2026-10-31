from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, require_staff
from app.db.session import get_db
from app.models import User
from app.schemas.common import Page
from app.schemas.report import OverdueInvoiceResponse, RevenueResponse, SummaryResponse
from app.services import report_service as service

router = APIRouter()


@router.get("/summary", response_model=SummaryResponse)
def get_summary(db: Session = Depends(get_db), _: User = Depends(require_staff)):
    return service.summary(db)


@router.get("/revenue", response_model=RevenueResponse)
def get_revenue(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    group_by: Literal["day", "month"] = Query("month"),
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    return service.revenue(db, date_from, date_to, group_by)


@router.get("/overdue", response_model=Page[OverdueInvoiceResponse])
def get_overdue(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    items, total = service.overdue_invoices(db, params.offset, params.page_size)
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)