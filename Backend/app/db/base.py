from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, MetaData, Numeric
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# BIGINT on MySQL, INTEGER on SQLite (so autoincrement works in tests)
BigInt = BigInteger().with_variant(Integer, "sqlite")
# Money is always DECIMAL, never FLOAT
Money = Numeric(12, 2)
Rate = Numeric(5, 2)


def utcnow() -> datetime:
    """Timestamps are always stored in UTC (naive datetime)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enum_type(enum_cls, length: int = 30):
    """Store enums as VARCHAR (not native ENUM) so migrations stay simple."""
    return SAEnum(enum_cls, native_enum=False, length=length, validate_strings=True)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)