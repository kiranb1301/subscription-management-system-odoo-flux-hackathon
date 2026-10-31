import uuid
from datetime import date, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.permissions import is_staff
from app.db.base import utcnow
from app.models import Invoice, Payment, PaymentAllocation, User
from app.models.enums import InvoiceStatus as I
from app.models.enums import PaymentMethod, PaymentStatus as P
from app.schemas.payment import PaymentAllocationResponse, PaymentCreate, PaymentResponse
from app.services.access import authorize_customer_access, get_customer_id_for_user
from app.services.invoice_service import _note, _record, mark_overdue
from app.services.pricing import money

PAYABLE = (I.CONFIRMED, I.PARTIALLY_PAID, I.OVERDUE)

_LOAD = (
    selectinload(Payment.customer),
    selectinload(Payment.allocations).selectinload(PaymentAllocation.invoice),
)


# ---------------- invoice status ----------------
def _derived_status(inv: Invoice) -> I:
    if inv.paid_amount >= inv.total_amount:
        return I.PAID
    if inv.due_date < date.today():
        return I.OVERDUE
    if inv.paid_amount > 0:
        return I.PARTIALLY_PAID
    return I.CONFIRMED


def _sync_invoice(db: Session, inv: Invoice, user_id: int | None, reason: str) -> None:
    new = _derived_status(inv)
    if new != inv.status:
        _record(db, inv, new, user_id, reason)
    else:
        _note(db, inv, user_id, reason)


# ---------------- responses ----------------
def to_responses(payments: list[Payment], staff: bool) -> list[PaymentResponse]:
    out = []
    for p in payments:
        out.append(
            PaymentResponse(
                id=p.id,
                payment_reference=p.payment_reference,
                customer_id=p.customer_id,
                customer_name=p.customer.name,
                method=p.method,
                amount=p.amount,
                payment_date=p.payment_date,
                status=p.status,
                note=p.note if staff else None,
                available_actions=["refund"] if staff and p.status == P.COMPLETED else [],
                allocations=[
                    PaymentAllocationResponse(
                        invoice_id=a.invoice_id,
                        invoice_number=a.invoice.invoice_number,
                        allocated_amount=a.allocated_amount,
                        allocated_at=a.allocated_at,
                    )
                    for a in sorted(p.allocations, key=lambda x: x.id)
                ],
            )
        )
    return out


# ---------------- reads ----------------
def get_payment(db: Session, payment_id: int) -> Payment:
    payment = db.scalar(
        select(Payment)
        .where(Payment.id == payment_id)
        .options(*_LOAD)
        .execution_options(populate_existing=True)
    )
    if payment is None:
        raise NotFoundError("Payment not found")
    return payment


def get_payment_for_user(db: Session, user: User, payment_id: int) -> Payment:
    payment = get_payment(db, payment_id)
    authorize_customer_access(db, user, payment.customer_id)
    return payment


def list_payments(
    db: Session,
    user: User,
    offset: int,
    limit: int,
    status: P | None = None,
    method: PaymentMethod | None = None,
    customer_id: int | None = None,
    invoice_id: int | None = None,
    search: str | None = None,
) -> tuple[list[Payment], int]:
    query = select(Payment)
    if is_staff(user):
        if customer_id is not None:
            query = query.where(Payment.customer_id == customer_id)
    else:
        own_id = get_customer_id_for_user(db, user)
        if own_id is None:
            return [], 0
        query = query.where(Payment.customer_id == own_id)
    if status is not None:
        query = query.where(Payment.status == status)
    if method is not None:
        query = query.where(Payment.method == method)
    if invoice_id is not None:
        query = query.where(
            Payment.id.in_(
                select(PaymentAllocation.payment_id).where(PaymentAllocation.invoice_id == invoice_id)
            )
        )
    if search:
        query = query.where(Payment.payment_reference.like(f"%{search.strip()}%"))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(*_LOAD).order_by(Payment.id.desc()).offset(offset).limit(limit)
    ).all()
    return list(items), total


# ---------------- record ----------------
def record_payment(db: Session, user: User, data: PaymentCreate) -> Payment:
    mark_overdue(db)

    if data.invoice_id is not None:
        wanted = [(data.invoice_id, data.amount)]
    else:
        wanted = [(a.invoice_id, a.amount) for a in data.allocations or []]
    ids = [invoice_id for invoice_id, _ in wanted]
    if len(set(ids)) != len(ids):
        raise AppError("An invoice can appear only once in a payment")
    if sum((amount for _, amount in wanted), Decimal("0")) != data.amount:
        raise AppError("Allocations must add up to the payment amount")

    invoices = {
        inv.id: inv
        for inv in db.scalars(
            select(Invoice)
            .where(Invoice.id.in_(ids), Invoice.is_deleted.is_(False))
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    }
    for invoice_id in ids:
        if invoice_id not in invoices:
            raise NotFoundError("Invoice not found")

    owners = {inv.customer_id for inv in invoices.values()}
    if len(owners) > 1:
        raise AppError("All invoices in one payment must belong to the same customer")
    customer_id = owners.pop()
    if data.customer_id is not None and data.customer_id != customer_id:
        raise AppError("The invoice does not belong to this customer")

    for invoice_id, amount in wanted:
        inv = invoices[invoice_id]
        if inv.status not in PAYABLE:
            raise AppError(
                f"Invoice {inv.invoice_number} cannot accept payments in status {inv.status.value}"
            )
        balance = inv.total_amount - inv.paid_amount
        if amount > balance:
            raise AppError(
                f"Payment of {amount} exceeds the balance due ({balance}) on invoice {inv.invoice_number}"
            )

    reference = data.payment_reference
    if reference is not None and db.scalar(
        select(Payment.id).where(Payment.payment_reference == reference)
    ):
        raise ConflictError("Payment reference already exists")

    paid_at = data.payment_date or utcnow()
    if paid_at.tzinfo is not None:
        paid_at = paid_at.astimezone(timezone.utc).replace(tzinfo=None)

    payment = Payment(
        payment_reference=reference or f"TMP-{uuid.uuid4().hex}",
        customer_id=customer_id,
        method=data.method,
        amount=data.amount,
        payment_date=paid_at,
        note=data.note,
        status=P.COMPLETED,
    )
    db.add(payment)
    try:
        db.flush()
        if reference is None:
            payment.payment_reference = f"PAY-{date.today().year}-{payment.id:06d}"
        for invoice_id, amount in wanted:
            inv = invoices[invoice_id]
            db.add(
                PaymentAllocation(
                    payment_id=payment.id, invoice_id=invoice_id, allocated_amount=amount
                )
            )
            inv.paid_amount = money(inv.paid_amount + amount)
            _sync_invoice(db, inv, user.id, f"Payment {payment.payment_reference} of {amount} received")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("Payment reference already exists")
    return get_payment(db, payment.id)


# ---------------- refund ----------------
def refund_payment(db: Session, user: User, payment_id: int, reason: str | None) -> Payment:
    mark_overdue(db)
    payment = get_payment(db, payment_id)
    if payment.status != P.COMPLETED:
        raise AppError(f"Payment cannot be refunded from status {payment.status.value}")

    for alloc in payment.allocations:
        inv = db.get(Invoice, alloc.invoice_id)
        remaining = inv.paid_amount - alloc.allocated_amount
        inv.paid_amount = money(remaining if remaining > 0 else Decimal("0"))
        _sync_invoice(db, inv, user.id, f"Payment {payment.payment_reference} refunded")

    payment.status = P.REFUNDED
    line = f"Refunded: {reason}" if reason else "Refunded"
    payment.note = f"{payment.note}\n{line}" if payment.note else line
    db.commit()
    return get_payment(db, payment.id)