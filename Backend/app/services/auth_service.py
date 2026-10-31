from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import roles
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Customer, Role, User
from app.schemas.auth import RegisterRequest


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(
        select(User).where(User.email == email.lower(), User.is_deleted.is_(False))
    )


def register_customer(db: Session, data: RegisterRequest) -> User:
    email = data.email.lower()
    if get_user_by_email(db, email):
        raise ConflictError("Email is already registered")

    role = db.scalar(select(Role).where(Role.name == roles.CUSTOMER))
    if role is None:
        raise RuntimeError("Roles are not seeded. Run: python -m app.db.seed")

    user = User(
        full_name=data.full_name,
        email=email,
        password_hash=hash_password(data.password),
        role_id=role.id,
    )
    db.add(user)
    db.flush()
    db.add(Customer(user_id=user.id, name=data.full_name, email=email))

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("Email is already registered")

    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise ForbiddenError("This account is disabled")
    return user


def issue_token(user: User) -> str:
    return create_access_token(str(user.id))