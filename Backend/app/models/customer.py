from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigInt, IdMixin, SoftDeleteMixin, TimestampMixin


class Customer(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "customers"

    # Optional link to a login account (customer portal)
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    company_name: Mapped[Optional[str]] = mapped_column(String(200))
    tax_id: Mapped[Optional[str]] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[Optional["User"]] = relationship()
    addresses: Mapped[list["CustomerAddress"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )


class CustomerAddress(IdMixin, TimestampMixin, Base):
    __tablename__ = "customer_addresses"

    customer_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    address_type: Mapped[str] = mapped_column(String(20), default="BILLING", nullable=False)
    line1: Mapped[str] = mapped_column(String(255), nullable=False)
    line2: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[Optional[str]] = mapped_column(String(100))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(100), default="India", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    customer: Mapped["Customer"] = relationship(back_populates="addresses")