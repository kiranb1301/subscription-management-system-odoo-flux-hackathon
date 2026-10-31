from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError
from app.models import Invoice, Payment, Subscription
from app.models.enums import BillingInterval as B
from app.models.enums import InvoiceStatus as I
from app.models.enums import PaymentStatus as P
from app.models.enums import SubscriptionStatus as S
from app.schemas.report import (
    OverdueInvoiceResponse,
    RevenuePoint,
    RevenueResponse,
    SummaryResponse,
)
from app.services.invoice_service import mark_overdue
from app.services.pricing import money

OPEN = (I.CONFIRMED, I.PARTIALLY_PAID, I.OVERDUE)

# how many billing intervals fit in one month
_PER_MONTH = {
    B.DAILY: Decimal("365") / Decimal("12"),
    B.WEEKLY: Decimal("52") / Decimal("12"),
    B.MONTHLY: Decimal("1"),
    B.YEARLY: Decimal("1") / Decimal("12"),
}


def _monthly_value(sub: Subscription) -> Decimal:
    """Recurring amount per billing cycle (before tax), normalised to one month."""
    cycle = sum(
        (money(l.unit_price * l.quantity) - l.discount_amount for l in sub.lines), Decimal("0")
    )
    plan = sub.plan
    per_month = _PER_MONTH[plan.billing_interval] / Decimal(plan.interval_count or 1)
    return cycle * per_month


def _mrr(db: Session) -> tuple[Decimal, int]:
    subs = db.scalars(
        select(Subscription)
        .where(Subscription.is_deleted.is_(False), Subscription.status == S.ACTIVE)
        .options(selectinload(Subscription.plan), selectinload(Subscription.lines))
    ).all()
    total = sum((_monthly_value(s) for s in subs), Decimal("0"))
    return money(total), len(subs)


def summary(db: Session) -> SummaryResponse:
    mark_overdue(db)
    mrr, active = _mrr(db)

    sub_counts = {s.value: 0 for s in S}
    for status, n in db.execute(
        select(Subscription.status, func.count())
        .where(Subscription.is_deleted.is_(False))
        .group_by(Subscription.status)
    ).all():
        sub_counts[status.value] = n

    inv_counts = {s.value: 0 for s in I}
    balances: dict[I, Decimal] = defaultdict(lambda: Decimal("0"))
    for status, n, balance in db.execute(
        select(Invoice.status, func.count(), func.coalesce(func.sum(Invoice.total_amount - Invoice.paid_amount), 0))
        .where(Invoice.is_deleted.is_(False))
        .group_by(Invoice.status)
    ).all():
        inv_counts[status.value] = n
        balances[status] = Decimal(balance)

    paid = {
        status: Decimal(total)
        for status, total in db.execute(
            select(Payment.status, func.coalesce(func.sum(Payment.amount), 0)).group_by(Payment.status)
        ).all()
    }
    return SummaryResponse(
        mrr=mrr,
        arr=money(mrr * 12),
        active_subscriptions=active,
        subscriptions_by_status=sub_counts,
        revenue_collected=money(paid.get(P.COMPLETED, Decimal("0"))),
        refunded_total=money(paid.get(P.REFUNDED, Decimal("0"))),
        outstanding_amount=money(sum((balances[s] for s in OPEN), Decimal("0"))),
        outstanding_count=sum(inv_counts[s.value] for s in OPEN),
        overdue_amount=money(balances[I.OVERDUE]),
        overdue_count=inv_counts[I.OVERDUE.value],
        invoices_by_status=inv_counts,
    )


def revenue(
    db: Session, date_from: date | None, date_to: date | None, group_by: str
) -> RevenueResponse:
    if date_from and date_to and date_from > date_to:
        raise AppError("'from' cannot be after 'to'")
    query = select(Payment).where(Payment.status.in_([P.COMPLETED, P.REFUNDED]))
    if date_from:
        query = query.where(Payment.payment_date >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.where(Payment.payment_date < datetime.combine(date_to + timedelta(days=1), time.min))

    fmt = "%Y-%m" if group_by == "month" else "%Y-%m-%d"
    buckets: dict[str, list] = defaultdict(lambda: [Decimal("0"), 0])
    refunded = Decimal("0")
    for p in db.scalars(query.order_by(Payment.payment_date)).all():
        if p.status == P.REFUNDED:
            refunded += p.amount
            continue
        bucket = buckets[p.payment_date.strftime(fmt)]
        bucket[0] += p.amount
        bucket[1] += 1
    points = [RevenuePoint(period=k, amount=money(v[0]), payments=v[1]) for k, v in sorted(buckets.items())]
    return RevenueResponse(
        group_by=group_by,
        date_from=date_from,
        date_to=date_to,
        total_collected=money(sum((p.amount for p in points), Decimal("0"))),
        total_refunded=money(refunded),
        points=points,
    )


def overdue_invoices(db: Session, offset: int, limit: int) -> tuple[list[OverdueInvoiceResponse], int]:
    mark_overdue(db)
    query = select(Invoice).where(Invoice.is_deleted.is_(False), Invoice.status == I.OVERDUE)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.options(selectinload(Invoice.customer))
        .order_by(Invoice.due_date, Invoice.id)
        .offset(offset)
        .limit(limit)
    ).all()
    today = date.today()
    items = [
        OverdueInvoiceResponse(
            invoice_id=i.id,
            invoice_number=i.invoice_number,
            customer_id=i.customer_id,
            customer_name=i.customer.name,
            due_date=i.due_date,
            days_overdue=(today - i.due_date).days,
            total_amount=i.total_amount,
            paid_amount=i.paid_amount,
            balance_due=i.total_amount - i.paid_amount,
        )
        for i in rows
    ]
    return items, total