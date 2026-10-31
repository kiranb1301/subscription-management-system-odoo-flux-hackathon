from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.permissions import is_staff
from app.models import Customer, User


def get_customer_id_for_user(db: Session, user: User) -> int | None:
    return db.scalar(
        select(Customer.id).where(
            Customer.user_id == user.id, Customer.is_deleted.is_(False)
        )
    )


def authorize_customer_access(db: Session, user: User, customer_id: int) -> None:
    """Ownership rule used by every customer-owned resource.

    Staff may access any customer. A customer may access only their own data.
    Anything else returns 404 (not 403) so IDs cannot be probed.
    """
    if is_staff(user):
        return
    if get_customer_id_for_user(db, user) != customer_id:
        raise NotFoundError("Resource not found")