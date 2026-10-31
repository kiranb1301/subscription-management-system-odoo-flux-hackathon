from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError, NotFoundError
from app.models import Plan, Product, ProductVariant, QuotationTemplate, QuotationTemplateLine
from app.schemas.quotation_template import TemplateCreate, TemplateLineIn, TemplateUpdate
from app.services.helpers import clean_changes


def _check_plan(db: Session, plan_id: int) -> None:
    plan = db.get(Plan, plan_id)
    if plan is None or not plan.is_active:
        raise AppError(f"Plan {plan_id} does not exist or is inactive")


def _build_lines(db: Session, items: list[TemplateLineIn]) -> list[QuotationTemplateLine]:
    lines = []
    for item in items:
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
            QuotationTemplateLine(
                product_id=item.product_id,
                variant_id=item.variant_id,
                description=item.description,
                quantity=item.quantity,
            )
        )
    return lines


def get_template(db: Session, template_id: int) -> QuotationTemplate:
    template = db.scalar(
        select(QuotationTemplate)
        .where(QuotationTemplate.id == template_id)
        .options(selectinload(QuotationTemplate.lines))
        .execution_options(populate_existing=True)
    )
    if template is None:
        raise NotFoundError("Quotation template not found")
    return template


def list_templates(
    db: Session,
    offset: int,
    limit: int,
    search: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[QuotationTemplate], int]:
    query = select(QuotationTemplate)
    if is_active is not None:
        query = query.where(QuotationTemplate.is_active.is_(is_active))
    if search:
        query = query.where(QuotationTemplate.name.like(f"%{search.strip()}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(selectinload(QuotationTemplate.lines))
        .order_by(QuotationTemplate.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return list(items), total


def create_template(db: Session, data: TemplateCreate) -> QuotationTemplate:
    if data.plan_id is not None:
        _check_plan(db, data.plan_id)
    template = QuotationTemplate(**data.model_dump(exclude={"lines"}))
    template.lines = _build_lines(db, data.lines)
    db.add(template)
    db.commit()
    return get_template(db, template.id)


def update_template(db: Session, template_id: int, data: TemplateUpdate) -> QuotationTemplate:
    template = get_template(db, template_id)
    lines = _build_lines(db, data.lines) if data.lines is not None else None
    changes = clean_changes(
        data.model_dump(exclude_unset=True, exclude={"lines"}),
        nullable=("plan_id", "description"),
    )
    if changes.get("plan_id") is not None:
        _check_plan(db, changes["plan_id"])
    for field, value in changes.items():
        setattr(template, field, value)
    if lines is not None:
        template.lines.clear()
        db.flush()
        template.lines.extend(lines)
    db.commit()
    return get_template(db, template.id)


def deactivate_template(db: Session, template_id: int) -> None:
    template = get_template(db, template_id)
    template.is_active = False
    db.commit()