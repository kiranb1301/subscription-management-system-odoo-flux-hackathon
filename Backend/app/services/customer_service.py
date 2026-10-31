from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models import Customer


def get_customer(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.is_deleted:
        raise NotFoundError("Resource not found")
    return customer


def list_customers(
    db: Session, offset: int, limit: int, search: str | None = None
) -> tuple[list[Customer], int]:
    query = select(Customer).where(Customer.is_deleted.is_(False))
    if search:
        like = f"%{search.strip()}%"
        query = query.where(or_(Customer.name.like(like), Customer.email.like(like)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Customer.id).offset(offset).limit(limit)).all()
    return list(items), total


def update_customer(db: Session, customer: Customer, changes: dict) -> Customer:
    for field, value in changes.items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return customer