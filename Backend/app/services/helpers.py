from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError


def clean_changes(changes: dict, nullable: tuple[str, ...] = ()) -> dict:
    """Drop explicit nulls for columns that cannot be NULL."""
    return {k: v for k, v in changes.items() if v is not None or k in nullable}


def commit_or_conflict(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError(message)