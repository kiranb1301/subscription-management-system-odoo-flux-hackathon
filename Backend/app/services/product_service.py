from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models import (
    Plan,
    PlanProduct,
    Product,
    ProductTax,
    ProductVariant,
    ProductVariantOption,
    Tax,
)
from app.schemas.product import ProductCreate, ProductUpdate, VariantCreate, VariantUpdate
from app.services.helpers import clean_changes, commit_or_conflict

VARIANT_NAME_TAKEN = "A variant with this name already exists for this product"

_PRODUCT_LOAD = (
    selectinload(Product.variants).selectinload(ProductVariant.options),
    selectinload(Product.product_taxes).selectinload(ProductTax.tax),
)


def _resolve_taxes(db: Session, tax_ids: list[int]) -> list[Tax]:
    unique_ids = list(dict.fromkeys(tax_ids))
    if not unique_ids:
        return []
    found = {t.id: t for t in db.scalars(select(Tax).where(Tax.id.in_(unique_ids))).all()}
    missing = [i for i in unique_ids if i not in found or not found[i].is_active]
    if missing:
        raise AppError(f"Unknown or inactive tax id(s): {missing}")
    return [found[i] for i in unique_ids]


def _used_in_active_plan(db: Session, product_id: int, variant_id: int | None = None) -> bool:
    query = (
        select(func.count())
        .select_from(PlanProduct)
        .join(Plan, Plan.id == PlanProduct.plan_id)
        .where(PlanProduct.product_id == product_id, Plan.is_active.is_(True))
    )
    if variant_id is not None:
        query = query.where(PlanProduct.variant_id == variant_id)
    return (db.scalar(query) or 0) > 0


# ---------------- products ----------------
def get_product(db: Session, product_id: int, staff: bool = True) -> Product:
    query = (
        select(Product)
        .where(Product.id == product_id, Product.is_deleted.is_(False))
        .options(*_PRODUCT_LOAD)
        .execution_options(populate_existing=True)
    )
    if not staff:
        query = query.where(Product.is_active.is_(True))
    product = db.scalar(query)
    if product is None:
        raise NotFoundError("Product not found")
    return product


def list_products(
    db: Session,
    offset: int,
    limit: int,
    staff: bool,
    search: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[Product], int]:
    query = select(Product).where(Product.is_deleted.is_(False))
    if not staff:
        query = query.where(Product.is_active.is_(True))
    elif is_active is not None:
        query = query.where(Product.is_active.is_(is_active))
    if search:
        query = query.where(Product.name.like(f"%{search.strip()}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(*_PRODUCT_LOAD).order_by(Product.id).offset(offset).limit(limit)
    ).all()
    return list(items), total


def create_product(db: Session, data: ProductCreate) -> Product:
    taxes = _resolve_taxes(db, data.tax_ids)
    product = Product(
        name=data.name,
        product_type=data.product_type,
        sales_price=data.sales_price,
        cost_price=data.cost_price,
        notes=data.notes,
        is_active=data.is_active,
    )
    product.product_taxes = [ProductTax(tax_id=t.id) for t in taxes]
    db.add(product)
    db.commit()
    return get_product(db, product.id)


def update_product(db: Session, product_id: int, data: ProductUpdate) -> Product:
    product = get_product(db, product_id)
    taxes = _resolve_taxes(db, data.tax_ids) if data.tax_ids is not None else None
    changes = clean_changes(
        data.model_dump(exclude_unset=True, exclude={"tax_ids"}), nullable=("notes",)
    )
    for field, value in changes.items():
        setattr(product, field, value)
    if taxes is not None:
        product.product_taxes.clear()
        db.flush()
        product.product_taxes.extend(ProductTax(tax_id=t.id) for t in taxes)
    db.commit()
    return get_product(db, product.id)


def delete_product(db: Session, product_id: int) -> None:
    product = get_product(db, product_id)
    if _used_in_active_plan(db, product.id):
        raise ConflictError("Product is used by active plans. Remove it from those plans first")
    product.is_deleted = True
    product.is_active = False
    if hasattr(product, "deleted_at"):
        product.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()


# ---------------- variants ----------------
def get_variant(db: Session, product_id: int, variant_id: int) -> ProductVariant:
    variant = db.scalar(
        select(ProductVariant)
        .where(ProductVariant.id == variant_id, ProductVariant.product_id == product_id)
        .options(selectinload(ProductVariant.options))
        .execution_options(populate_existing=True)
    )
    if variant is None:
        raise NotFoundError("Variant not found")
    return variant


def _variant_name_taken(
    db: Session, product_id: int, name: str, exclude_id: int | None = None
) -> bool:
    query = select(ProductVariant.id).where(
        ProductVariant.product_id == product_id,
        func.lower(ProductVariant.variant_name) == name.lower(),
    )
    if exclude_id is not None:
        query = query.where(ProductVariant.id != exclude_id)
    return db.scalar(query) is not None


def create_variant(db: Session, product_id: int, data: VariantCreate) -> ProductVariant:
    get_product(db, product_id)  # 404 if missing or deleted
    if _variant_name_taken(db, product_id, data.variant_name):
        raise ConflictError(VARIANT_NAME_TAKEN)
    variant = ProductVariant(
        product_id=product_id,
        variant_name=data.variant_name,
        additional_price=data.additional_price,
        is_active=data.is_active,
        options=[
            ProductVariantOption(option_name=o.option_name, option_value=o.option_value)
            for o in data.options
        ],
    )
    db.add(variant)
    commit_or_conflict(db, VARIANT_NAME_TAKEN)
    return get_variant(db, product_id, variant.id)


def update_variant(
    db: Session, product_id: int, variant_id: int, data: VariantUpdate
) -> ProductVariant:
    get_product(db, product_id)
    variant = get_variant(db, product_id, variant_id)
    changes = clean_changes(data.model_dump(exclude_unset=True, exclude={"options"}))
    if "variant_name" in changes and _variant_name_taken(
        db, product_id, changes["variant_name"], exclude_id=variant.id
    ):
        raise ConflictError(VARIANT_NAME_TAKEN)
    for field, value in changes.items():
        setattr(variant, field, value)
    if data.options is not None:
        variant.options.clear()
        db.flush()
        variant.options.extend(
            ProductVariantOption(option_name=o.option_name, option_value=o.option_value)
            for o in data.options
        )
    commit_or_conflict(db, VARIANT_NAME_TAKEN)
    return get_variant(db, product_id, variant.id)


def deactivate_variant(db: Session, product_id: int, variant_id: int) -> None:
    get_product(db, product_id)
    variant = get_variant(db, product_id, variant_id)
    if _used_in_active_plan(db, product_id, variant.id):
        raise ConflictError("Variant is used by active plans. Remove it from those plans first")
    variant.is_active = False
    db.commit()