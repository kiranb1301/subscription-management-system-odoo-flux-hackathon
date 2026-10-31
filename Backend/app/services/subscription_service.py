import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.permissions import is_staff
from app.models import (
    Quotation,
    Subscription,
    SubscriptionLine,
    SubscriptionStatusHistory,
    User,
)
from app.models.enums import QuotationStatus
from app.models.enums import SubscriptionStatus as S
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionLineResponse,
    SubscriptionResponse,
)
from app.services.access import authorize_customer_access, get_customer_id_for_user
from app.services.dates import advance_date

REQ_CANCEL = "REQUEST_CANCEL"
REQ_RENEW = "REQUEST_RENEW"

_LOAD = (
    selectinload(Subscription.lines),
    selectinload(Subscription.customer),
    selectinload(Subscription.plan),
    selectinload(Subscription.status_history),
)


# ---------------- history helpers ----------------
def _record(db: Session, sub: Subscription, to: S, user_id: int | None, reason: str | None) -> None:
    """Change status and write a history row."""
    db.add(
        SubscriptionStatusHistory(
            subscription_id=sub.id,
            from_status=sub.status,
            to_status=to,
            changed_by=user_id,
            reason=reason[:255] if reason else None,
        )
    )
    sub.status = to


def _note(db: Session, sub: Subscription, user_id: int | None, reason: str) -> None:
    """History row without a status change (renewals, requests, declines)."""
    db.add(
        SubscriptionStatusHistory(
            subscription_id=sub.id,
            from_status=sub.status,
            to_status=sub.status,
            changed_by=user_id,
            reason=reason[:255],
        )
    )


def pending_request(sub: Subscription) -> str | None:
    """A request stays pending until any later history row is written."""
    rows = sorted(sub.status_history, key=lambda h: h.id)
    if not rows:
        return None
    reason = rows[-1].reason or ""
    if reason.startswith(REQ_CANCEL):
        return "CANCEL"
    if reason.startswith(REQ_RENEW):
        return "RENEW"
    return None


# ---------------- rules ----------------
def _can_close(sub: Subscription) -> bool:
    if sub.status not in (S.ACTIVE, S.PAUSED):
        return False
    reached = sub.expiry_date is not None and sub.expiry_date <= date.today()
    return sub.plan.allow_early_close or reached


def _can_renew(sub: Subscription) -> bool:
    return (
        sub.status in (S.ACTIVE, S.EXPIRED)
        and sub.plan.allow_renewal
        and sub.expiry_date is not None
    )


def available_actions(sub: Subscription, staff: bool) -> list[str]:
    plan, st, pending = sub.plan, sub.status, pending_request(sub)
    actions: list[str] = []
    if staff:
        if st == S.CONFIRMED:
            actions += ["activate", "cancel"]
        elif st == S.ACTIVE:
            if plan.allow_pause:
                actions.append("pause")
            if _can_close(sub):
                actions.append("close")
            actions.append("cancel")
            if _can_renew(sub):
                actions.append("renew")
        elif st == S.PAUSED:
            actions.append("resume")
            if _can_close(sub):
                actions.append("close")
            actions.append("cancel")
        elif st == S.EXPIRED and _can_renew(sub):
            actions.append("renew")
        if pending:
            actions.append("dismiss_request")
    else:
        if st == S.ACTIVE and plan.allow_pause:
            actions.append("pause")
        if st == S.PAUSED:
            actions.append("resume")
        if st in (S.CONFIRMED, S.ACTIVE, S.PAUSED) and pending != "CANCEL":
            actions.append("request_cancel")
        if _can_renew(sub) and pending != "RENEW":
            actions.append("request_renew")
    return actions


def _require_status(sub: Subscription, allowed: tuple, action: str) -> None:
    if sub.status not in allowed:
        raise AppError(f"Subscription cannot be {action} from status {sub.status.value}")


def build_response(sub: Subscription, staff: bool) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=sub.id,
        subscription_number=sub.subscription_number,
        customer_id=sub.customer_id,
        customer_name=sub.customer.name,
        plan_id=sub.plan_id,
        plan_name=sub.plan.name,
        billing_interval=sub.plan.billing_interval,
        interval_count=sub.plan.interval_count,
        quotation_id=sub.quotation_id,
        status=sub.status,
        start_date=sub.start_date,
        expiry_date=sub.expiry_date,
        next_billing_date=sub.next_billing_date,
        payment_terms_days=sub.payment_terms_days,
        pending_request=pending_request(sub),
        available_actions=available_actions(sub, staff),
        lines=[
            SubscriptionLineResponse.model_validate(line)
            for line in sorted(sub.lines, key=lambda x: x.id)
        ],
    )


# ---------------- reads ----------------
def expire_due(db: Session) -> None:
    """Lazy expiry: ACTIVE/PAUSED subscriptions past their expiry date."""
    rows = db.scalars(
        select(Subscription)
        .where(
            Subscription.is_deleted.is_(False),
            Subscription.status.in_([S.ACTIVE, S.PAUSED]),
            Subscription.expiry_date.is_not(None),
            Subscription.expiry_date < date.today(),
        )
        .options(selectinload(Subscription.plan))
    ).all()
    for sub in rows:
        target = S.CLOSED if sub.plan.auto_close else S.EXPIRED
        _record(db, sub, target, None, "Reached expiry date")
        sub.next_billing_date = None
    if rows:
        db.commit()


def get_subscription(db: Session, subscription_id: int) -> Subscription:
    expire_due(db)
    sub = db.scalar(
        select(Subscription)
        .where(Subscription.id == subscription_id, Subscription.is_deleted.is_(False))
        .options(*_LOAD)
        .execution_options(populate_existing=True)
    )
    if sub is None:
        raise NotFoundError("Subscription not found")
    return sub


def get_subscription_for_user(db: Session, user: User, subscription_id: int) -> Subscription:
    """Ownership rule: customers see only their own subscriptions (404 otherwise)."""
    sub = get_subscription(db, subscription_id)
    authorize_customer_access(db, user, sub.customer_id)
    return sub


def _pending_request_ids():
    latest = select(func.max(SubscriptionStatusHistory.id)).group_by(
        SubscriptionStatusHistory.subscription_id
    )
    return select(SubscriptionStatusHistory.subscription_id).where(
        SubscriptionStatusHistory.id.in_(latest),
        or_(
            SubscriptionStatusHistory.reason.like(f"{REQ_CANCEL}%"),
            SubscriptionStatusHistory.reason.like(f"{REQ_RENEW}%"),
        ),
    )


def list_subscriptions(
    db: Session,
    user: User,
    offset: int,
    limit: int,
    status: S | None = None,
    customer_id: int | None = None,
    search: str | None = None,
    has_request: bool | None = None,
) -> tuple[list[Subscription], int]:
    expire_due(db)
    query = select(Subscription).where(Subscription.is_deleted.is_(False))
    if is_staff(user):
        if customer_id is not None:
            query = query.where(Subscription.customer_id == customer_id)
        if has_request is not None:
            pending_ids = _pending_request_ids()
            if has_request:
                query = query.where(Subscription.id.in_(pending_ids))
            else:
                query = query.where(Subscription.id.not_in(pending_ids))
    else:
        own_id = get_customer_id_for_user(db, user)
        if own_id is None:
            return [], 0
        query = query.where(Subscription.customer_id == own_id)
    if status is not None:
        query = query.where(Subscription.status == status)
    if search:
        query = query.where(Subscription.subscription_number.like(f"%{search.strip()}%"))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(*_LOAD).order_by(Subscription.id.desc()).offset(offset).limit(limit)
    ).all()
    return list(items), total


def list_history(db: Session, user: User, subscription_id: int) -> list[SubscriptionStatusHistory]:
    sub = get_subscription_for_user(db, user, subscription_id)
    return sorted(sub.status_history, key=lambda h: h.id)


# ---------------- staff actions ----------------
def create_subscription(db: Session, data: SubscriptionCreate, user: User) -> Subscription:
    quotation = db.scalar(
        select(Quotation)
        .where(Quotation.id == data.quotation_id, Quotation.is_deleted.is_(False))
        .options(selectinload(Quotation.lines), selectinload(Quotation.customer))
    )
    if quotation is None:
        raise NotFoundError("Quotation not found")
    if quotation.status != QuotationStatus.CONFIRMED:
        raise AppError(
            "Only confirmed quotations can become subscriptions "
            f"(current status: {quotation.status.value})"
        )
    customer = quotation.customer
    if customer.is_deleted or not customer.is_active:
        raise AppError("Customer is inactive")

    existing = db.scalar(
        select(Subscription.id).where(
            Subscription.quotation_id == quotation.id,
            Subscription.is_deleted.is_(False),
            Subscription.status != S.CANCELLED,
        )
    )
    if existing is not None:
        raise ConflictError("A subscription already exists for this quotation")

    today = date.today()
    sub = Subscription(
        subscription_number=f"TMP-{uuid.uuid4().hex}",
        customer_id=quotation.customer_id,
        plan_id=quotation.plan_id,
        quotation_id=quotation.id,
        start_date=today,  # placeholder until activation
        payment_terms_days=data.payment_terms_days,
        status=S.CONFIRMED,
        created_by=user.id,
    )
    sub.lines = [
        SubscriptionLine(
            product_id=line.product_id,
            variant_id=line.variant_id,
            description=line.description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            discount_amount=line.discount_amount,
            tax_rate=line.tax_rate,
            line_total=line.line_total,
        )
        for line in quotation.lines
    ]
    db.add(sub)
    db.flush()
    sub.subscription_number = f"SUB-{today.year}-{sub.id:06d}"
    db.add(
        SubscriptionStatusHistory(
            subscription_id=sub.id,
            from_status=None,
            to_status=S.CONFIRMED,
            changed_by=user.id,
            reason=f"Created from quotation {quotation.quotation_number}",
        )
    )
    db.commit()
    return get_subscription(db, sub.id)


def activate(db: Session, user: User, subscription_id: int, start_date: date | None) -> Subscription:
    sub = get_subscription(db, subscription_id)
    _require_status(sub, (S.CONFIRMED,), "activated")
    start = start_date or date.today()
    if start < date.today():
        raise AppError("start_date cannot be in the past")
    plan = sub.plan
    if plan.end_date is not None and plan.end_date < start:
        raise AppError("The plan has already ended. Choose another plan")
    sub.start_date = start
    sub.expiry_date = plan.end_date
    sub.next_billing_date = start
    _record(db, sub, S.ACTIVE, user.id, "Activated")
    db.commit()
    return get_subscription(db, sub.id)


def close(db: Session, user: User, subscription_id: int) -> Subscription:
    sub = get_subscription(db, subscription_id)
    _require_status(sub, (S.ACTIVE, S.PAUSED), "closed")
    if not _can_close(sub):
        raise AppError("This plan does not allow closing before the expiry date")
    sub.next_billing_date = None
    _record(db, sub, S.CLOSED, user.id, "Closed by staff")
    db.commit()
    return get_subscription(db, sub.id)


def cancel(db: Session, user: User, subscription_id: int, reason: str | None) -> Subscription:
    sub = get_subscription(db, subscription_id)
    _require_status(sub, (S.CONFIRMED, S.ACTIVE, S.PAUSED), "cancelled")
    sub.next_billing_date = None
    _record(db, sub, S.CANCELLED, user.id, f"Cancelled: {reason}" if reason else "Cancelled by staff")
    db.commit()
    return get_subscription(db, sub.id)


def renew(db: Session, user: User, subscription_id: int, periods: int) -> Subscription:
    sub = get_subscription(db, subscription_id)
    _require_status(sub, (S.ACTIVE, S.EXPIRED), "renewed")
    plan = sub.plan
    if not plan.allow_renewal:
        raise AppError("This plan does not allow renewal")
    if sub.expiry_date is None:
        raise AppError("This subscription has no expiry date to extend")

    today = date.today()
    base = sub.expiry_date if sub.status == S.ACTIVE else max(sub.expiry_date, today)
    sub.expiry_date = advance_date(base, plan.billing_interval, plan.interval_count * periods)
    reason = f"Renewed for {periods} period(s)"
    if sub.status == S.EXPIRED:
        sub.next_billing_date = today
        _record(db, sub, S.ACTIVE, user.id, reason)
    else:
        _note(db, sub, user.id, reason)
    db.commit()
    return get_subscription(db, sub.id)


def dismiss_request(db: Session, user: User, subscription_id: int, reason: str | None) -> Subscription:
    sub = get_subscription(db, subscription_id)
    if pending_request(sub) is None:
        raise AppError("There is no pending request on this subscription")
    _note(db, sub, user.id, f"Request declined: {reason}" if reason else "Request declined")
    db.commit()
    return get_subscription(db, sub.id)


# ---------------- owner or staff actions ----------------
def pause(db: Session, user: User, subscription_id: int) -> Subscription:
    sub = get_subscription_for_user(db, user, subscription_id)
    _require_status(sub, (S.ACTIVE,), "paused")
    if not sub.plan.allow_pause:
        raise AppError("This plan does not allow pausing")
    _record(db, sub, S.PAUSED, user.id, "Paused by staff" if is_staff(user) else "Paused by customer")
    db.commit()
    return get_subscription(db, sub.id)


def resume(db: Session, user: User, subscription_id: int) -> Subscription:
    sub = get_subscription_for_user(db, user, subscription_id)
    _require_status(sub, (S.PAUSED,), "resumed")
    today = date.today()
    if sub.next_billing_date is None or sub.next_billing_date < today:
        sub.next_billing_date = today
    _record(db, sub, S.ACTIVE, user.id, "Resumed by staff" if is_staff(user) else "Resumed by customer")
    db.commit()
    return get_subscription(db, sub.id)


# ---------------- customer requests ----------------
def request_cancel(db: Session, user: User, subscription_id: int, reason: str | None) -> Subscription:
    sub = get_subscription_for_user(db, user, subscription_id)
    _require_status(sub, (S.CONFIRMED, S.ACTIVE, S.PAUSED), "cancelled")
    if pending_request(sub) == "CANCEL":
        raise ConflictError("A cancellation request is already pending")
    _note(db, sub, user.id, REQ_CANCEL + (f": {reason}" if reason else ""))
    db.commit()
    return get_subscription(db, sub.id)


def request_renew(db: Session, user: User, subscription_id: int, reason: str | None) -> Subscription:
    sub = get_subscription_for_user(db, user, subscription_id)
    _require_status(sub, (S.ACTIVE, S.EXPIRED), "renewed")
    if not sub.plan.allow_renewal:
        raise AppError("This plan does not allow renewal")
    if sub.expiry_date is None:
        raise AppError("This subscription has no expiry date to extend")
    if pending_request(sub) == "RENEW":
        raise ConflictError("A renewal request is already pending")
    _note(db, sub, user.id, REQ_RENEW + (f": {reason}" if reason else ""))
    db.commit()
    return get_subscription(db, sub.id)