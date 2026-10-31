from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigInt, IdMixin, Money, TimestampMixin, enum_type, utcnow
from app.models.enums import DiscountType


class Discount(IdMixin, TimestampMixin, Base):
    __tablename__ = "discounts"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    discount_type: Mapped[DiscountType] = mapped_column(
        enum_type(DiscountType, 20), default=DiscountType.PERCENTAGE, nullable=False
    )
    discount_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    usage_limit: Mapped[Optional[int]] = mapped_column(Integer)
    per_customer_limit: Mapped[Optional[int]] = mapped_column(Integer)
    min_purchase_amount: Mapped[Optional[Decimal]] = mapped_column(Money)
    min_quantity: Mapped[Optional[int]] = mapped_column(Integer)
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product_mappings: Mapped[list["DiscountProductMapping"]] = relationship(
        back_populates="discount", cascade="all, delete-orphan"
    )
    usages: Mapped[list["DiscountUsage"]] = relationship(back_populates="discount")


class DiscountProductMapping(IdMixin, Base):
    __tablename__ = "discount_product_mappings"
    __table_args__ = (UniqueConstraint("discount_id", "product_id"),)

    discount_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("discounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )

    discount: Mapped["Discount"] = relationship(back_populates="product_mappings")
    product: Mapped["Product"] = relationship()


class DiscountUsage(IdMixin, Base):
    __tablename__ = "discount_usages"

    discount_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("discounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    subscription_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("subscriptions.id", ondelete="SET NULL"), index=True
    )
    invoice_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("invoices.id", ondelete="SET NULL"), index=True
    )
    amount_applied: Mapped[Decimal] = mapped_column(Money, nullable=False)
    used_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    discount: Mapped["Discount"] = relationship(back_populates="usages")
    customer: Mapped["Customer"] = relationship()
    subscription: Mapped[Optional["Subscription"]] = relationship()
    invoice: Mapped[Optional["Invoice"]] = relationship()