import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError, NotFoundError
from app.core.permissions import is_staff
from app.models import (
    Customer,
    Plan,
    PlanProduct,
    Product,
    ProductTax,
    ProductVariant,
    Quotation,
    QuotationLine,
    QuotationTemplate,
    User,
)
from app.models.enums import QuotationStatus
from app.schemas.quotation import QuotationCreate, QuotationLineIn, QuotationUpdate
from app.services.access import authorize_customer_access, get_customer_id_for_user
from app.services.helpers import clean_changes

CENT = Decimal("0.01")
DEFAULT_VALIDITY_DAYS = 30

_LOAD = (
    selectinload(Quotation.lines),
    selectinload(Quotation.customer),
    selectinload(Quotation.plan),
)


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


# ---------------- pricing ----------------
def _price_line(db: Session, plan: Plan, item: QuotationLineIn) -> QuotationLine:
    product = db.scalar(
        select(Product)
        .where(Product.id == item.product_id, Product.is_deleted.is_(False))
        .options(selectinload(Product.product_taxes).selectinload(ProductTax.tax))
    )
    if product is None or not product.is_active:
        raise AppError(f"Product {item.product_id} does not exist or is inactive")

    variant = None
    if item.variant_id is not None:
        variant = db.scalar(
            select(ProductVariant).where(
                ProductVariant.id == item.variant_id,
                ProductVariant.product_id == item.product_id,
            )
        )
        if variant is None or not variant.is_active:
            raise AppError(
                f"Variant {item.variant_id} does not belong to product "
                f"{item.product_id} or is inactive"
            )

    if item.unit_price is not None:
        unit_price = item.unit_price
    else:
        override_query = select(PlanProduct.unit_price).where(
            PlanProduct.plan_id == plan.id, PlanProduct.product_id == product.id
        )
        if item.variant_id is None:
            override_query = override_query.where(PlanProduct.variant_id.is_(None))
        else:
            override_query = override_query.where(PlanProduct.variant_id == item.variant_id)
        override = db.scalar(override_query)
        if override is not None:
            unit_price = override
        else:
            unit_price = product.sales_price + (
                variant.additional_price if variant is not None else Decimal("0.00")
            )

    gross = _money(unit_price * item.quantity)
    discount = _money(item.discount_amount)
    if discount > gross:
        raise AppError("Line discount cannot exceed the line amount")
    taxable = gross - discount
    tax_rate = sum(
        (pt.tax.rate for pt in product.product_taxes if pt.tax.is_active), Decimal("0.00")
    )
    tax_amount = _money(taxable * tax_rate / Decimal("100"))

    description = item.description or (
        f"{product.name} - {variant.variant_name}" if variant is not None else product.name
    )
    return QuotationLine(
        product_id=product.id,
        variant_id=item.variant_id,
        description=description[:255],
        quantity=item.quantity,
        unit_price=_money(unit_price),
        discount_amount=discount,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        line_total=taxable + tax_amount,
    )


def _apply_totals(quotation: Quotation) -> None:
    subtotal = sum((l.unit_price * l.quantity for l in quotation.lines), Decimal("0"))
    discount = sum((l.discount_amount for l in quotation.lines), Decimal("0"))
    tax = sum((l.tax_amount for l in quotation.lines), Decimal("0"))
    quotation.subtotal = _money(subtotal)
    quotation.discount_amount = _money(discount)
    quotation.tax_amount = _money(tax)
    quotation.total_amount = _money(subtotal - discount + tax)


# ---------------- reads ----------------
def _expire_if_needed(db: Session, quotation: Quotation) -> None:
    """Only SENT quotes expire automatically; drafts are still being worked on."""
    if (
        quotation.status == QuotationStatus.SENT
        and quotation.valid_until is not None
        and quotation.valid_until < date.today()
    ):
        quotation.status = QuotationStatus.EXPIRED
        db.commit()
        db.refresh(quotation)


def get_quotation(db: Session, quotation_id: int) -> Quotation:
    quotation = db.scalar(
        select(Quotation)
        .where(Quotation.id == quotation_id, Quotation.is_deleted.is_(False))
        .options(*_LOAD)
        .execution_options(populate_existing=True)
    )
    if quotation is None:
        raise NotFoundError("Quotation not found")
    _expire_if_needed(db, quotation)
    return quotation


def get_quotation_for_user(db: Session, user: User, quotation_id: int) -> Quotation:
    """Ownership rule: customers see only their own quotes, and never drafts."""
    quotation = get_quotation(db, quotation_id)
    authorize_customer_access(db, user, quotation.customer_id)
    if not is_staff(user) and quotation.status == QuotationStatus.DRAFT:
        raise NotFoundError("Quotation not found")
    return quotation


def list_quotations(
    db: Session,
    user: User,
    offset: int,
    limit: int,
    status: QuotationStatus | None = None,
    customer_id: int | None = None,
    search: str | None = None,
) -> tuple[list[Quotation], int]:
    db.execute(
        update(Quotation)
        .where(
            Quotation.status == QuotationStatus.SENT,
            Quotation.valid_until.is_not(None),
            Quotation.valid_until < date.today(),
        )
        .values(status=QuotationStatus.EXPIRED)
    )
    db.commit()

    query = select(Quotation).where(Quotation.is_deleted.is_(False))
    if is_staff(user):
        if customer_id is not None:
            query = query.where(Quotation.customer_id == customer_id)
    else:
        own_id = get_customer_id_for_user(db, user)
        if own_id is None:
            return [], 0
        query = query.where(
            Quotation.customer_id == own_id, Quotation.status != QuotationStatus.DRAFT
        )
    if status is not None:
        query = query.where(Quotation.status == status)
    if search:
        query = query.where(Quotation.quotation_number.like(f"%{search.strip()}%"))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(*_LOAD).order_by(Quotation.id.desc()).offset(offset).limit(limit)
    ).all()
    return list(items), total


# ---------------- writes (staff) ----------------
def _check_valid_until(valid_until: date) -> None:
    if valid_until < date.today():
        raise AppError("valid_until cannot be in the past")


def create_quotation(db: Session, data: QuotationCreate, user: User) -> Quotation:
    customer = db.scalar(
        select(Customer).where(Customer.id == data.customer_id, Customer.is_deleted.is_(False))
    )
    if customer is None:
        raise NotFoundError("Customer not found")
    if not customer.is_active:
        raise AppError("Customer is inactive")

    template = None
    if data.template_id is not None:
        template = db.scalar(
            select(QuotationTemplate)
            .where(QuotationTemplate.id == data.template_id)
            .options(selectinload(QuotationTemplate.lines))
        )
        if template is None or not template.is_active:
            raise AppError("Quotation template does not exist or is inactive")

    plan_id = data.plan_id or (template.plan_id if template is not None else None)
    if plan_id is None:
        raise AppError("plan_id is required when the template has no plan")
    plan = db.get(Plan, plan_id)
    if plan is None or not plan.is_active:
        raise AppError(f"Plan {plan_id} does not exist or is inactive")

    items = list(data.lines)
    if not items and template is not None:
        items = [
            QuotationLineIn(
                product_id=l.product_id,
                variant_id=l.variant_id,
                description=l.description,
                quantity=l.quantity,
            )
            for l in template.lines
        ]
    if not items:
        raise AppError("A quotation needs at least one line")

    today = date.today()
    valid_until = data.valid_until or today + timedelta(
        days=template.validity_days if template is not None else DEFAULT_VALIDITY_DAYS
    )
    _check_valid_until(valid_until)

    quotation = Quotation(
        quotation_number=f"TMP-{uuid.uuid4().hex}",
        customer_id=customer.id,
        plan_id=plan.id,
        template_id=template.id if template is not None else None,
        status=QuotationStatus.DRAFT,
        quotation_date=today,
        valid_until=valid_until,
        notes=data.notes,
        created_by=user.id,
    )
    quotation.lines = [_price_line(db, plan, item) for item in items]
    _apply_totals(quotation)
    db.add(quotation)
    db.flush()
    quotation.quotation_number = f"QT-{today.year}-{quotation.id:06d}"
    db.commit()
    return get_quotation(db, quotation.id)


def _require_status(quotation: Quotation, expected: QuotationStatus, action: str) -> None:
    if quotation.status != expected:
        raise AppError(
            f"Only {expected.value.lower()} quotations can be {action} "
            f"(current status: {quotation.status.value})"
        )


def update_quotation(db: Session, quotation_id: int, data: QuotationUpdate) -> Quotation:
    quotation = get_quotation(db, quotation_id)
    _require_status(quotation, QuotationStatus.DRAFT, "edited")

    changes = clean_changes(
        data.model_dump(exclude_unset=True, exclude={"lines"}), nullable=("notes",)
    )
    if "valid_until" in changes:
        _check_valid_until(changes["valid_until"])
    lines = None
    if data.lines is not None:
        if not data.lines:
            raise AppError("A quotation needs at least one line")
        lines = [_price_line(db, quotation.plan, item) for item in data.lines]

    for field, value in changes.items():
        setattr(quotation, field, value)
    if lines is not None:
        quotation.lines.clear()
        db.flush()
        quotation.lines.extend(lines)
        _apply_totals(quotation)
    db.commit()
    return get_quotation(db, quotation.id)


def delete_quotation(db: Session, quotation_id: int) -> None:
    quotation = get_quotation(db, quotation_id)
    _require_status(quotation, QuotationStatus.DRAFT, "deleted")
    quotation.is_deleted = True
    db.commit()


# ---------------- status transitions ----------------
def send_quotation(db: Session, quotation_id: int) -> Quotation:
    quotation = get_quotation(db, quotation_id)
    _require_status(quotation, QuotationStatus.DRAFT, "sent")
    if quotation.valid_until is not None and quotation.valid_until < date.today():
        raise AppError("The validity date has passed. Update valid_until before sending")
    quotation.status = QuotationStatus.SENT
    db.commit()
    return get_quotation(db, quotation.id)


def confirm_quotation(db: Session, user: User, quotation_id: int) -> Quotation:
    quotation = get_quotation_for_user(db, user, quotation_id)
    _require_status(quotation, QuotationStatus.SENT, "confirmed")
    quotation.status = QuotationStatus.CONFIRMED
    db.commit()
    return get_quotation(db, quotation.id)


def reject_quotation(db: Session, user: User, quotation_id: int) -> Quotation:
    quotation = get_quotation_for_user(db, user, quotation_id)
    _require_status(quotation, QuotationStatus.SENT, "rejected")
    quotation.status = QuotationStatus.REJECTED
    db.commit()
    return get_quotation(db, quotation.id)