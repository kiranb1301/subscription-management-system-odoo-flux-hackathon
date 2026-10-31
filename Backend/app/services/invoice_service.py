import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.permissions import is_staff
from app.db.base import utcnow
from app.models import (
    BillingJob,
    Discount,
    DiscountUsage,
    Invoice,
    InvoiceLine,
    InvoiceStatusHistory,
    Subscription,
    User,
)
from app.models.enums import BillingJobStatus, DiscountType
from app.models.enums import InvoiceStatus as I
from app.models.enums import SubscriptionStatus as S
from app.schemas.invoice import InvoiceResponse, InvoiceUpdate
from app.services.access import authorize_customer_access, get_customer_id_for_user
from app.services.dates import advance_date
from app.services.helpers import clean_changes
from app.services.pricing import line_amounts, money
from app.services.subscription_service import expire_due

logger = logging.getLogger(__name__)

MAX_PERIODS_PER_RUN = 12

_LOAD = (
    selectinload(Invoice.lines),
    selectinload(Invoice.customer),
    selectinload(Invoice.status_history),
    selectinload(Invoice.subscription).selectinload(Subscription.lines),
)


# ---------------- history and totals ----------------
def _record(db: Session, inv: Invoice, to: I, user_id: int | None, reason: str | None) -> None:
    db.add(
        InvoiceStatusHistory(
            invoice_id=inv.id,
            from_status=inv.status,
            to_status=to,
            changed_by=user_id,
            reason=reason[:255] if reason else None,
        )
    )
    inv.status = to


def _note(db: Session, inv: Invoice, user_id: int | None, reason: str) -> None:
    db.add(
        InvoiceStatusHistory(
            invoice_id=inv.id,
            from_status=inv.status,
            to_status=inv.status,
            changed_by=user_id,
            reason=reason[:255],
        )
    )


def _apply_totals(inv: Invoice) -> None:
    subtotal = sum((l.unit_price * l.quantity for l in inv.lines), Decimal("0"))
    discount = sum((l.discount_amount for l in inv.lines), Decimal("0"))
    tax = sum((l.tax_amount for l in inv.lines), Decimal("0"))
    inv.subtotal = money(subtotal)
    inv.discount_amount = money(discount)
    inv.tax_amount = money(tax)
    inv.total_amount = money(subtotal - discount + tax)


def _require_status(inv: Invoice, allowed: tuple, action: str) -> None:
    if inv.status not in allowed:
        raise AppError(f"Invoice cannot be {action} from status {inv.status.value}")


# ---------------- responses ----------------
def _discount_codes(db: Session, invoice_ids: list[int]) -> dict[int, str]:
    if not invoice_ids:
        return {}
    rows = db.execute(
        select(DiscountUsage.invoice_id, Discount.code)
        .join(Discount, Discount.id == DiscountUsage.discount_id)
        .where(DiscountUsage.invoice_id.in_(invoice_ids))
    ).all()
    return {invoice_id: code for invoice_id, code in rows}


def available_actions(inv: Invoice, staff: bool, has_discount: bool) -> list[str]:
    actions: list[str] = []
    if staff:
        if inv.status == I.DRAFT:
            actions += ["edit", "apply_discount"]
            if has_discount:
                actions.append("remove_discount")
            actions += ["confirm", "cancel"]
        elif inv.status in (I.CONFIRMED, I.OVERDUE) and inv.paid_amount == 0:
            actions.append("cancel")
    if staff or inv.status != I.DRAFT:
        actions.append("download_pdf")
    return actions


def to_responses(db: Session, invoices: list[Invoice], staff: bool) -> list[InvoiceResponse]:
    codes = _discount_codes(db, [i.id for i in invoices])
    return [
        InvoiceResponse(
            id=inv.id,
            invoice_number=inv.invoice_number,
            subscription_id=inv.subscription_id,
            subscription_number=inv.subscription.subscription_number,
            customer_id=inv.customer_id,
            customer_name=inv.customer.name,
            invoice_date=inv.invoice_date,
            due_date=inv.due_date,
            billing_period_start=inv.billing_period_start,
            billing_period_end=inv.billing_period_end,
            subtotal=inv.subtotal,
            discount_amount=inv.discount_amount,
            tax_amount=inv.tax_amount,
            total_amount=inv.total_amount,
            paid_amount=inv.paid_amount,
            balance_due=inv.total_amount - inv.paid_amount,
            status=inv.status,
            discount_code=codes.get(inv.id),
            notes=inv.notes if staff else None,
            available_actions=available_actions(inv, staff, inv.id in codes),
            lines=sorted(inv.lines, key=lambda x: x.id),
        )
        for inv in invoices
    ]


# ---------------- reads ----------------
def mark_overdue(db: Session) -> None:
    """Lazy: unpaid invoices past their due date become OVERDUE when anyone reads."""
    rows = db.scalars(
        select(Invoice).where(
            Invoice.is_deleted.is_(False),
            Invoice.status.in_([I.CONFIRMED, I.PARTIALLY_PAID]),
            Invoice.due_date < date.today(),
        )
    ).all()
    for inv in rows:
        _record(db, inv, I.OVERDUE, None, "Past due date")
    if rows:
        db.commit()


def get_invoice(db: Session, invoice_id: int) -> Invoice:
    mark_overdue(db)
    inv = db.scalar(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.is_deleted.is_(False))
        .options(*_LOAD)
        .execution_options(populate_existing=True)
    )
    if inv is None:
        raise NotFoundError("Invoice not found")
    return inv


def get_invoice_for_user(db: Session, user: User, invoice_id: int) -> Invoice:
    """Ownership rule: customers see only their own invoices, and never drafts."""
    inv = get_invoice(db, invoice_id)
    authorize_customer_access(db, user, inv.customer_id)
    if not is_staff(user) and inv.status == I.DRAFT:
        raise NotFoundError("Invoice not found")
    return inv


def list_invoices(
    db: Session,
    user: User,
    offset: int,
    limit: int,
    status: I | None = None,
    customer_id: int | None = None,
    subscription_id: int | None = None,
    search: str | None = None,
) -> tuple[list[Invoice], int]:
    mark_overdue(db)
    query = select(Invoice).where(Invoice.is_deleted.is_(False))
    if is_staff(user):
        if customer_id is not None:
            query = query.where(Invoice.customer_id == customer_id)
    else:
        own_id = get_customer_id_for_user(db, user)
        if own_id is None:
            return [], 0
        query = query.where(Invoice.customer_id == own_id, Invoice.status != I.DRAFT)
    if subscription_id is not None:
        query = query.where(Invoice.subscription_id == subscription_id)
    if status is not None:
        query = query.where(Invoice.status == status)
    if search:
        query = query.where(Invoice.invoice_number.like(f"%{search.strip()}%"))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(*_LOAD).order_by(Invoice.id.desc()).offset(offset).limit(limit)
    ).all()
    return list(items), total


def list_history(db: Session, user: User, invoice_id: int) -> list[InvoiceStatusHistory]:
    inv = get_invoice_for_user(db, user, invoice_id)
    return sorted(inv.status_history, key=lambda h: h.id)


# ---------------- generation ----------------
def _load_subscription(db: Session, subscription_id: int) -> Subscription:
    sub = db.scalar(
        select(Subscription)
        .where(Subscription.id == subscription_id, Subscription.is_deleted.is_(False))
        .options(selectinload(Subscription.plan), selectinload(Subscription.lines))
        .execution_options(populate_existing=True)
    )
    if sub is None:
        raise NotFoundError("Subscription not found")
    return sub


def _invoice_lines(sub: Subscription) -> list[InvoiceLine]:
    lines = []
    for line in sorted(sub.lines, key=lambda x: x.id):
        _, tax, total = line_amounts(
            line.unit_price, line.quantity, line.discount_amount, line.tax_rate
        )
        lines.append(
            InvoiceLine(
                product_id=line.product_id,
                variant_id=line.variant_id,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount_amount=money(line.discount_amount),
                tax_name=f"Tax {line.tax_rate:.2f}%" if line.tax_rate > 0 else None,
                tax_rate=line.tax_rate,
                tax_amount=tax,
                line_total=total,
            )
        )
    return lines


def _create_invoice(
    db: Session, sub: Subscription, run_date: date, user_id: int | None, reason: str
) -> Invoice | None:
    start = sub.next_billing_date
    plan = sub.plan
    end = advance_date(start, plan.billing_interval, plan.interval_count) - timedelta(days=1)
    already = db.scalar(
        select(Invoice.id).where(
            Invoice.subscription_id == sub.id,
            Invoice.billing_period_start == start,
            Invoice.billing_period_end == end,
        )
    )
    if already is not None:
        return None

    inv = Invoice(
        invoice_number=f"TMP-{uuid.uuid4().hex}",
        subscription_id=sub.id,
        customer_id=sub.customer_id,
        invoice_date=run_date,
        due_date=run_date + timedelta(days=sub.payment_terms_days),
        billing_period_start=start,
        billing_period_end=end,
        status=I.DRAFT,
    )
    inv.lines = _invoice_lines(sub)
    _apply_totals(inv)
    db.add(inv)
    db.flush()
    inv.invoice_number = f"INV-{run_date.year}-{inv.id:06d}"
    db.add(
        InvoiceStatusHistory(
            invoice_id=inv.id, from_status=None, to_status=I.DRAFT, changed_by=user_id, reason=reason
        )
    )
    return inv


def bill_subscription(
    db: Session,
    sub: Subscription,
    run_date: date,
    user_id: int | None,
    reason: str,
    max_periods: int,
) -> list[Invoice]:
    """Create one draft invoice per due period and move next_billing_date forward."""
    created: list[Invoice] = []
    plan = sub.plan
    for _ in range(max_periods):
        start = sub.next_billing_date
        if start is None or start > run_date:
            break
        if sub.expiry_date is not None and start > sub.expiry_date:
            break
        invoice = _create_invoice(db, sub, run_date, user_id, reason)
        if invoice is not None:
            created.append(invoice)
        sub.next_billing_date = advance_date(start, plan.billing_interval, plan.interval_count)
    return created


def run_billing(db: Session, user: User, run_date: date | None = None) -> BillingJob:
    today = date.today()
    run_date = run_date or today
    if run_date > today:
        raise AppError("run_date cannot be in the future")
    expire_due(db)

    job = BillingJob(
        job_type="GENERATE_INVOICES",
        run_date=run_date,
        status=BillingJobStatus.RUNNING,
        started_at=utcnow(),
    )
    db.add(job)
    db.commit()
    job_id = job.id

    sub_ids = list(
        db.scalars(
            select(Subscription.id)
            .where(
                Subscription.is_deleted.is_(False),
                Subscription.status == S.ACTIVE,
                Subscription.next_billing_date.is_not(None),
                Subscription.next_billing_date <= run_date,
                or_(
                    Subscription.expiry_date.is_(None),
                    Subscription.next_billing_date <= Subscription.expiry_date,
                ),
            )
            .order_by(Subscription.id)
        ).all()
    )

    processed = created = 0
    errors: list[str] = []
    for sub_id in sub_ids:
        try:
            sub = _load_subscription(db, sub_id)
            new = bill_subscription(
                db, sub, run_date, user.id, f"Generated by billing run {job_id}", MAX_PERIODS_PER_RUN
            )
            db.commit()
            processed += 1
            created += len(new)
        except Exception as exc:  # one bad subscription must not stop the run
            db.rollback()
            logger.exception("Billing failed for subscription %s", sub_id)
            errors.append(f"subscription {sub_id}: {exc}")

    job = db.get(BillingJob, job_id)
    job.finished_at = utcnow()
    job.subscriptions_processed = processed
    job.invoices_created = created
    job.status = BillingJobStatus.FAILED if errors else BillingJobStatus.COMPLETED
    job.error_message = "; ".join(errors)[:2000] if errors else None
    db.commit()
    db.refresh(job)
    return job


def list_jobs(db: Session, offset: int, limit: int) -> tuple[list[BillingJob], int]:
    total = db.scalar(select(func.count()).select_from(BillingJob)) or 0
    items = db.scalars(
        select(BillingJob).order_by(BillingJob.id.desc()).offset(offset).limit(limit)
    ).all()
    return list(items), total


def generate_for_subscription(db: Session, user: User, subscription_id: int) -> Invoice:
    expire_due(db)
    sub = _load_subscription(db, subscription_id)
    if sub.status != S.ACTIVE:
        raise AppError("Only active subscriptions can be invoiced")
    today = date.today()
    if sub.next_billing_date is None or sub.next_billing_date > today:
        raise AppError("No invoice is due for this subscription yet")
    try:
        created = bill_subscription(db, sub, today, user.id, "Generated manually", 1)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("This billing period has already been invoiced")
    if not created:
        raise AppError("Nothing to invoice for this subscription")
    return get_invoice(db, created[0].id)


# ---------------- draft editing ----------------
def update_invoice(db: Session, invoice_id: int, data: InvoiceUpdate) -> Invoice:
    inv = get_invoice(db, invoice_id)
    _require_status(inv, (I.DRAFT,), "edited")
    changes = clean_changes(data.model_dump(exclude_unset=True), nullable=("notes",))
    due = changes.get("due_date")
    if due is not None and due < inv.invoice_date:
        raise AppError("due_date cannot be before the invoice date")
    for field, value in changes.items():
        setattr(inv, field, value)
    db.commit()
    return get_invoice(db, inv.id)


def _release_discount(db: Session, inv: Invoice) -> str | None:
    """Delete discount usage rows for this invoice and give the uses back."""
    usages = db.scalars(select(DiscountUsage).where(DiscountUsage.invoice_id == inv.id)).all()
    code = None
    for usage in usages:
        discount = db.get(Discount, usage.discount_id)
        code = discount.code if discount is not None else code
        db.execute(
            update(Discount)
            .where(Discount.id == usage.discount_id, Discount.used_count > 0)
            .values(used_count=Discount.used_count - 1)
        )
        db.delete(usage)
    return code


def apply_discount(db: Session, user: User, invoice_id: int, code: str) -> Invoice:
    inv = get_invoice(db, invoice_id)
    _require_status(inv, (I.DRAFT,), "discounted")

    code = code.strip().upper()
    discount = db.scalar(
        select(Discount)
        .where(Discount.code == code)
        .options(selectinload(Discount.product_mappings))
        .execution_options(populate_existing=True)
    )
    if discount is None or not discount.is_active:
        raise AppError("Discount code is invalid or inactive")
    if db.scalar(select(DiscountUsage.id).where(DiscountUsage.invoice_id == inv.id)) is not None:
        raise ConflictError("A discount is already applied to this invoice")

    today = date.today()
    if (discount.start_date and today < discount.start_date) or (
        discount.end_date and today > discount.end_date
    ):
        raise AppError("Discount code is not valid today")
    if discount.usage_limit is not None and discount.used_count >= discount.usage_limit:
        raise AppError("Discount usage limit has been reached")
    if discount.per_customer_limit is not None:
        used_by_customer = db.scalar(
            select(func.count())
            .select_from(DiscountUsage)
            .where(
                DiscountUsage.discount_id == discount.id,
                DiscountUsage.customer_id == inv.customer_id,
            )
        ) or 0
        if used_by_customer >= discount.per_customer_limit:
            raise AppError("This customer has already used the discount the maximum number of times")

    mapped = {m.product_id for m in discount.product_mappings}
    eligible = [l for l in inv.lines if not mapped or l.product_id in mapped]
    if not eligible:
        raise AppError("This discount does not apply to any line of the invoice")

    nets = [money(l.unit_price * l.quantity) - l.discount_amount for l in eligible]
    base = sum(nets, Decimal("0"))
    quantity = sum(l.quantity for l in eligible)
    if discount.min_purchase_amount is not None and base < discount.min_purchase_amount:
        raise AppError("The invoice is below the minimum purchase amount for this discount")
    if discount.min_quantity is not None and quantity < discount.min_quantity:
        raise AppError("The invoice is below the minimum quantity for this discount")

    if discount.discount_type == DiscountType.PERCENTAGE:
        amount = money(base * discount.discount_value / Decimal("100"))
    else:
        amount = money(discount.discount_value)
    amount = min(amount, base)
    if amount <= 0:
        raise AppError("This discount would not reduce the invoice")

    claimed = db.execute(
        update(Discount)
        .where(
            Discount.id == discount.id,
            or_(Discount.usage_limit.is_(None), Discount.used_count < Discount.usage_limit),
        )
        .values(used_count=Discount.used_count + 1)
    )
    if claimed.rowcount == 0:
        db.rollback()
        raise AppError("Discount usage limit has been reached")

    applied = Decimal("0")
    for index, (line, net) in enumerate(zip(eligible, nets)):
        if index == len(eligible) - 1:
            share = amount - applied
        else:
            share = money(amount * net / base)
        share = min(share, net)
        line.discount_amount = line.discount_amount + share
        applied += share
        _, tax, total = line_amounts(
            line.unit_price, line.quantity, line.discount_amount, line.tax_rate
        )
        line.tax_amount = tax
        line.line_total = total
    _apply_totals(inv)

    db.add(
        DiscountUsage(
            discount_id=discount.id,
            customer_id=inv.customer_id,
            subscription_id=inv.subscription_id,
            invoice_id=inv.id,
            amount_applied=applied,
        )
    )
    _note(db, inv, user.id, f"Discount {code} applied")
    db.commit()
    return get_invoice(db, inv.id)


def remove_discount(db: Session, user: User, invoice_id: int) -> Invoice:
    inv = get_invoice(db, invoice_id)
    _require_status(inv, (I.DRAFT,), "changed")
    code = _release_discount(db, inv)
    if code is None:
        raise AppError("No discount is applied to this invoice")
    # Draft lines come from the subscription, so rebuilding them undoes the discount
    inv.lines.clear()
    db.flush()
    inv.lines.extend(_invoice_lines(inv.subscription))
    _apply_totals(inv)
    _note(db, inv, user.id, f"Discount {code} removed")
    db.commit()
    return get_invoice(db, inv.id)


# ---------------- status changes ----------------
def confirm_invoice(db: Session, user: User, invoice_id: int) -> Invoice:
    inv = get_invoice(db, invoice_id)
    _require_status(inv, (I.DRAFT,), "confirmed")
    if inv.total_amount == 0:
        _record(db, inv, I.PAID, user.id, "Confirmed with nothing to pay")
    else:
        _record(db, inv, I.CONFIRMED, user.id, "Confirmed")
    db.commit()
    return get_invoice(db, inv.id)


def cancel_invoice(db: Session, user: User, invoice_id: int, reason: str | None) -> Invoice:
    inv = get_invoice(db, invoice_id)
    _require_status(inv, (I.DRAFT, I.CONFIRMED, I.OVERDUE), "cancelled")
    if inv.paid_amount > 0:
        raise AppError("Invoices with payments cannot be cancelled")
    _release_discount(db, inv)
    _record(db, inv, I.CANCELLED, user.id, f"Cancelled: {reason}" if reason else "Cancelled")
    db.commit()
    return get_invoice(db, inv.id)