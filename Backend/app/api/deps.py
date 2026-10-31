from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import permissions
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Customer, User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Not authenticated")

    subject = decode_access_token(credentials.credentials)
    if subject is None or not subject.isdigit():
        raise UnauthorizedError("Invalid or expired token")

    user = db.get(User, int(subject))
    if user is None or user.is_deleted or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


def require_roles(*allowed: str):
    """Usage: Depends(require_roles(roles.ADMIN))"""

    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.name not in allowed:
            raise ForbiddenError("You do not have permission to perform this action")
        return current_user

    return checker


require_admin = require_roles(*permissions.ADMIN_ONLY)
require_staff = require_roles(*permissions.STAFF)


def get_current_customer(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Customer:
    customer = db.scalar(
        select(Customer).where(
            Customer.user_id == current_user.id, Customer.is_deleted.is_(False)
        )
    )
    if customer is None:
        raise NotFoundError("No customer profile is linked to this account")
    return customer


class PageParams:
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size