from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError, NotFoundError
from app.models import Plan, PlanProduct, Product, ProductVariant
from app.schemas.plan import PlanCreate, PlanProductIn, PlanUpdate
from app.services.helpers import clean_changes

_PLAN_LOAD = (
    selectinload(Plan.plan_products).selectinload(PlanProduct.product),
    selectinload(Plan.plan_products).selectinload(PlanProduct.variant),
)


def _available_now(query):
    """What a customer may see: active and inside the plan's date window."""
    today = date.today()
    return query.where(
        Plan.is_active.is_(True),
        or_(Plan.start_date.is_(None), Plan.start_date <= today),
        or_(Plan.end_date.is_(None), Plan.end_date >= today),
    )


def _build_lines(db: Session, items: list[PlanProductIn]) -> list[PlanProduct]:
    seen: set[tuple[int, int | None]] = set()
    lines: list[PlanProduct] = []
    for item in items:
        key = (item.product_id, item.variant_id)
        if key in seen:
            raise AppError("The same product and variant appear more than once in this plan")
        seen.add(key)

        product = db.scalar(
            select(Product).where(Product.id == item.product_id, Product.is_deleted.is_(False))
        )
        if product is None or not product.is_active:
            raise AppError(f"Product {item.product_id} does not exist or is inactive")

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

        lines.append(
            PlanProduct(
                product_id=item.product_id,
                variant_id=item.variant_id,
                default_quantity=item.default_quantity,
                unit_price=item.unit_price,
            )
        )
    return lines


def get_plan(db: Session, plan_id: int, staff: bool = True) -> Plan:
    query = (
        select(Plan)
        .where(Plan.id == plan_id)
        .options(*_PLAN_LOAD)
        .execution_options(populate_existing=True)
    )
    if not staff:
        query = _available_now(query)
    plan = db.scalar(query)
    if plan is None:
        raise NotFoundError("Plan not found")
    return plan


def list_plans(
    db: Session,
    offset: int,
    limit: int,
    staff: bool,
    search: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[Plan], int]:
    query = select(Plan)
    if not staff:
        query = _available_now(query)
    elif is_active is not None:
        query = query.where(Plan.is_active.is_(is_active))
    if search:
        query = query.where(Plan.name.like(f"%{search.strip()}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(*_PLAN_LOAD).order_by(Plan.id).offset(offset).limit(limit)
    ).all()
    return list(items), total


def create_plan(db: Session, data: PlanCreate) -> Plan:
    lines = _build_lines(db, data.products)
    plan = Plan(**data.model_dump(exclude={"products"}))
    plan.plan_products = lines
    db.add(plan)
    db.commit()
    return get_plan(db, plan.id)


def update_plan(db: Session, plan_id: int, data: PlanUpdate) -> Plan:
    plan = get_plan(db, plan_id)
    lines = _build_lines(db, data.products) if data.products is not None else None
    changes = clean_changes(
        data.model_dump(exclude_unset=True, exclude={"products"}),
        nullable=("start_date", "end_date"),
    )
    start = changes["start_date"] if "start_date" in changes else plan.start_date
    end = changes["end_date"] if "end_date" in changes else plan.end_date
    if start and end and end < start:
        raise AppError("end_date cannot be before start_date")

    for field, value in changes.items():
        setattr(plan, field, value)
    if lines is not None:
        plan.plan_products.clear()
        db.flush()
        plan.plan_products.extend(lines)
    db.commit()
    return get_plan(db, plan.id)


def deactivate_plan(db: Session, plan_id: int) -> None:
    plan = get_plan(db, plan_id)
    plan.is_active = False
    db.commit()