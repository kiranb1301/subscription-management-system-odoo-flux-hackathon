from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models import Discount, DiscountProductMapping, Product
from app.models.enums import DiscountType
from app.schemas.discount import DiscountCreate, DiscountUpdate
from app.services.helpers import clean_changes, commit_or_conflict

CODE_TAKEN = "A discount with this code already exists"
NULLABLE = (
    "start_date",
    "end_date",
    "usage_limit",
    "per_customer_limit",
    "min_purchase_amount",
    "min_quantity",
)


def _check_products(db: Session, product_ids: list[int]) -> list[int]:
    unique = list(dict.fromkeys(product_ids))
    if not unique:
        return []
    found = set(
        db.scalars(
            select(Product.id).where(Product.id.in_(unique), Product.is_deleted.is_(False))
        ).all()
    )
    missing = [i for i in unique if i not in found]
    if missing:
        raise AppError(f"Unknown product id(s): {missing}")
    return unique


def get_discount(db: Session, discount_id: int) -> Discount:
    discount = db.scalar(
        select(Discount)
        .where(Discount.id == discount_id)
        .options(selectinload(Discount.product_mappings))
        .execution_options(populate_existing=True)
    )
    if discount is None:
        raise NotFoundError("Discount not found")
    return discount


def list_discounts(
    db: Session,
    offset: int,
    limit: int,
    search: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[Discount], int]:
    query = select(Discount)
    if is_active is not None:
        query = query.where(Discount.is_active.is_(is_active))
    if search:
        like = f"%{search.strip()}%"
        query = query.where(or_(Discount.code.like(like), Discount.name.like(like)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(selectinload(Discount.product_mappings))
        .order_by(Discount.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return list(items), total


def create_discount(db: Session, data: DiscountCreate) -> Discount:
    if db.scalar(select(Discount.id).where(Discount.code == data.code)) is not None:
        raise ConflictError(CODE_TAKEN)
    product_ids = _check_products(db, data.product_ids)
    discount = Discount(**data.model_dump(exclude={"product_ids"}))
    discount.product_mappings = [DiscountProductMapping(product_id=i) for i in product_ids]
    db.add(discount)
    commit_or_conflict(db, CODE_TAKEN)
    return get_discount(db, discount.id)


def update_discount(db: Session, discount_id: int, data: DiscountUpdate) -> Discount:
    discount = get_discount(db, discount_id)
    product_ids = _check_products(db, data.product_ids) if data.product_ids is not None else None
    changes = clean_changes(
        data.model_dump(exclude_unset=True, exclude={"product_ids"}), nullable=NULLABLE
    )

    dtype = changes.get("discount_type", discount.discount_type)
    value = changes.get("discount_value", discount.discount_value)
    if dtype == DiscountType.PERCENTAGE and value > 100:
        raise AppError("A percentage discount cannot exceed 100")
    start = changes["start_date"] if "start_date" in changes else discount.start_date
    end = changes["end_date"] if "end_date" in changes else discount.end_date
    if start and end and end < start:
        raise AppError("end_date cannot be before start_date")
    new_limit = changes.get("usage_limit")
    if new_limit is not None and new_limit < discount.used_count:
        raise AppError("usage_limit cannot be lower than the number of times the code was used")

    for field, val in changes.items():
        setattr(discount, field, val)
    if product_ids is not None:
        discount.product_mappings.clear()
        db.flush()
        discount.product_mappings.extend(DiscountProductMapping(product_id=i) for i in product_ids)
    db.commit()
    return get_discount(db, discount.id)


def deactivate_discount(db: Session, discount_id: int) -> None:
    discount = get_discount(db, discount_id)
    discount.is_active = False
    db.commit()