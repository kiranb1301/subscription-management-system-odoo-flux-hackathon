import hashlib
import logging
import secrets
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.security import hash_password
from app.db.base import utcnow
from app.models import EmailVerificationToken, PasswordResetToken, User
from app.services.auth_service import get_user_by_email
from app.services.email_service import send_email
from app.settings import settings

logger = logging.getLogger(__name__)

INVALID = "Invalid or expired token"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------- email verification ----------------
def send_verification(db: Session, user: User) -> None:
    """Issue a fresh verification link. Never raises: registration must not fail on email."""
    try:
        now = utcnow()
        db.execute(
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.verified_at.is_(None),
                EmailVerificationToken.expires_at > now,
            )
            .values(expires_at=now)
        )
        token = secrets.token_urlsafe(32)
        db.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=_hash(token),
                expires_at=now + timedelta(hours=settings.EMAIL_VERIFY_EXPIRE_HOURS),
            )
        )
        db.commit()
        link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        send_email(
            user.email,
            "Verify your Brightloop email",
            f"Hi {user.full_name},\n\nConfirm your email address by opening this link:\n{link}\n\n"
            f"The link is valid for {settings.EMAIL_VERIFY_EXPIRE_HOURS} hours.",
        )
    except Exception:
        db.rollback()
        logger.exception("Could not issue verification email for user %s", user.id)


def verify_email(db: Session, token: str) -> None:
    row = db.scalar(select(EmailVerificationToken).where(EmailVerificationToken.token_hash == _hash(token)))
    now = utcnow()
    if row is None or row.verified_at is not None or row.expires_at < now:
        raise AppError(INVALID)
    user = db.get(User, row.user_id)
    if user is None or user.is_deleted:
        raise AppError(INVALID)
    user.is_email_verified = True
    row.verified_at = now
    db.commit()


def resend_verification(db: Session, user: User) -> None:
    if user.is_email_verified:
        raise AppError("Email is already verified")
    send_verification(db, user)


# ---------------- password reset ----------------
def request_password_reset(db: Session, email: str) -> None:
    """Silent for unknown or disabled accounts, so the endpoint never reveals who is registered."""
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        return
    now = utcnow()
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash(token),
            expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
        )
    )
    db.commit()
    link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    send_email(
        user.email,
        "Reset your Brightloop password",
        f"Hi {user.full_name},\n\nSomeone asked to reset your password. Open this link to choose a new one:\n{link}\n\n"
        f"The link is valid for {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes and works once. "
        "If this was not you, ignore this email.",
    )


def reset_password(db: Session, token: str, new_password: str) -> None:
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash(token)))
    now = utcnow()
    if row is None or row.used_at is not None or row.expires_at < now:
        raise AppError(INVALID)
    user = db.get(User, row.user_id)
    if user is None or user.is_deleted or not user.is_active:
        raise AppError(INVALID)
    user.password_hash = hash_password(new_password)
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    db.commit()