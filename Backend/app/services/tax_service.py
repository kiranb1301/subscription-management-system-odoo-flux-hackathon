from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Tax
from app.schemas.tax import TaxCreate, TaxUpdate
from app.services.helpers import clean_changes, commit_or_conflict

NAME_TAKEN = "A tax with this name already exists"


def _name_taken(db: Session, name: str, exclude_id: int | None = None) -> bool:
    query = select(Tax.id).where(func.lower(Tax.name) == name.lower())
    if exclude_id is not None:
        query = query.where(Tax.id != exclude_id)
    return db.scalar(query) is not None


def get_tax(db: Session, tax_id: int) -> Tax:
    tax = db.get(Tax, tax_id)
    if tax is None:
        raise NotFoundError("Tax not found")
    return tax


def list_taxes(
    db: Session, offset: int, limit: int, is_active: bool | None = None
) -> tuple[list[Tax], int]:
    query = select(Tax)
    if is_active is not None:
        query = query.where(Tax.is_active.is_(is_active))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Tax.id).offset(offset).limit(limit)).all()
    return list(items), total


def create_tax(db: Session, data: TaxCreate) -> Tax:
    if _name_taken(db, data.name):
        raise ConflictError(NAME_TAKEN)
    tax = Tax(name=data.name, rate=data.rate, is_active=data.is_active)
    db.add(tax)
    commit_or_conflict(db, NAME_TAKEN)
    db.refresh(tax)
    return tax


def update_tax(db: Session, tax_id: int, data: TaxUpdate) -> Tax:
    tax = get_tax(db, tax_id)
    changes = clean_changes(data.model_dump(exclude_unset=True))
    if "name" in changes and _name_taken(db, changes["name"], exclude_id=tax.id):
        raise ConflictError(NAME_TAKEN)
    for field, value in changes.items():
        setattr(tax, field, value)
    commit_or_conflict(db, NAME_TAKEN)
    db.refresh(tax)
    return tax


def deactivate_tax(db: Session, tax_id: int) -> None:
    tax = get_tax(db, tax_id)
    tax.is_active = False
    db.commit()