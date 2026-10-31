from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_user, require_roles, require_staff
from app.core import roles
from app.core.permissions import is_staff
from app.db.session import get_db
from app.models import User
from app.models.enums import SubscriptionStatus
from app.schemas.common import Page
from app.schemas.subscription import (
    ActivateRequest,
    HistoryResponse,
    ReasonRequest,
    RenewRequest,
    SubscriptionCreate,
    SubscriptionResponse,
)
from app.services import subscription_service as service

router = APIRouter()
require_customer = require_roles(roles.CUSTOMER)


@router.get("", response_model=Page[SubscriptionResponse])
def list_subscriptions(
    status: SubscriptionStatus | None = Query(None),
    customer_id: int | None = Query(None, description="Staff only; ignored for customers"),
    search: str | None = Query(None, description="Match on subscription number"),
    has_request: bool | None = Query(None, description="Staff only: pending customer requests"),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    staff = is_staff(current_user)
    items, total = service.list_subscriptions(
        db, current_user, params.offset, params.page_size, status, customer_id, search, has_request
    )
    return Page(
        items=[service.build_response(s, staff) for s in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
def get_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub = service.get_subscription_for_user(db, current_user, subscription_id)
    return service.build_response(sub, is_staff(current_user))


@router.get("/{subscription_id}/history", response_model=list[HistoryResponse])
def get_history(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    staff = is_staff(current_user)
    rows = service.list_history(db, current_user, subscription_id)
    return [
        HistoryResponse(
            from_status=h.from_status,
            to_status=h.to_status,
            reason=h.reason,
            changed_at=h.changed_at,
            changed_by=h.changed_by if staff else None,
        )
        for h in rows
    ]


@router.post("", response_model=SubscriptionResponse, status_code=201)
def create_subscription(
    payload: SubscriptionCreate,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    return service.build_response(service.create_subscription(db, payload, staff_user), True)


@router.post("/{subscription_id}/activate", response_model=SubscriptionResponse)
def activate_subscription(
    subscription_id: int,
    payload: ActivateRequest | None = None,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    start = payload.start_date if payload else None
    return service.build_response(service.activate(db, staff_user, subscription_id, start), True)


@router.post("/{subscription_id}/close", response_model=SubscriptionResponse)
def close_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    return service.build_response(service.close(db, staff_user, subscription_id), True)


@router.post("/{subscription_id}/cancel", response_model=SubscriptionResponse)
def cancel_subscription(
    subscription_id: int,
    payload: ReasonRequest | None = None,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    reason = (payload.reason if payload else None) or None
    return service.build_response(service.cancel(db, staff_user, subscription_id, reason), True)


@router.post("/{subscription_id}/renew", response_model=SubscriptionResponse)
def renew_subscription(
    subscription_id: int,
    payload: RenewRequest | None = None,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    periods = payload.periods if payload else 1
    return service.build_response(service.renew(db, staff_user, subscription_id, periods), True)


@router.post("/{subscription_id}/dismiss-request", response_model=SubscriptionResponse)
def dismiss_request(
    subscription_id: int,
    payload: ReasonRequest | None = None,
    db: Session = Depends(get_db),
    staff_user: User = Depends(require_staff),
):
    reason = (payload.reason if payload else None) or None
    return service.build_response(
        service.dismiss_request(db, staff_user, subscription_id, reason), True
    )


@router.post("/{subscription_id}/pause", response_model=SubscriptionResponse)
def pause_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub = service.pause(db, current_user, subscription_id)
    return service.build_response(sub, is_staff(current_user))


@router.post("/{subscription_id}/resume", response_model=SubscriptionResponse)
def resume_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub = service.resume(db, current_user, subscription_id)
    return service.build_response(sub, is_staff(current_user))


@router.post("/{subscription_id}/request-cancel", response_model=SubscriptionResponse)
def request_cancellation(
    subscription_id: int,
    payload: ReasonRequest | None = None,
    db: Session = Depends(get_db),
    customer_user: User = Depends(require_customer),
):
    reason = (payload.reason if payload else None) or None
    sub = service.request_cancel(db, customer_user, subscription_id, reason)
    return service.build_response(sub, False)


@router.post("/{subscription_id}/request-renew", response_model=SubscriptionResponse)
def request_renewal(
    subscription_id: int,
    payload: ReasonRequest | None = None,
    db: Session = Depends(get_db),
    customer_user: User = Depends(require_customer),
):
    reason = (payload.reason if payload else None) or None
    sub = service.request_renew(db, customer_user, subscription_id, reason)
    return service.build_response(sub, False)