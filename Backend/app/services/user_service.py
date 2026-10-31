from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.models import Role, User
from app.schemas.user import StaffCreateRequest
from app.services.auth_service import get_user_by_email


def create_staff(db: Session, data: StaffCreateRequest) -> User:
    email = data.email.lower()
    if get_user_by_email(db, email):
        raise ConflictError("Email is already registered")

    role = db.scalar(select(Role).where(Role.name == data.role))
    if role is None:
        raise RuntimeError("Roles are not seeded. Run: python -m app.db.seed")

    user = User(
        full_name=data.full_name,
        email=email,
        password_hash=hash_password(data.password),
        role_id=role.id,
        is_email_verified=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("Email is already registered")
    db.refresh(user)
    return user


def list_users(
    db: Session, offset: int, limit: int, role: str | None = None
) -> tuple[list[User], int]:
    query = select(User).where(User.is_deleted.is_(False))
    if role:
        query = query.join(Role).where(Role.name == role.upper())
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(User.id).offset(offset).limit(limit)).all()
    return list(items), total


def set_active(db: Session, acting_admin: User, user_id: int, is_active: bool) -> User:
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise NotFoundError("User not found")
    if user.id == acting_admin.id and not is_active:
        raise AppError("You cannot deactivate your own account")
    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user