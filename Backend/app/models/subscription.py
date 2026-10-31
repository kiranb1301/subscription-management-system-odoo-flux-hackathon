from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    BigInt,
    IdMixin,
    Money,
    Rate,
    SoftDeleteMixin,
    TimestampMixin,
    enum_type,
    utcnow,
)
from app.models.enums import SubscriptionStatus


class Subscription(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_status_next_billing_date", "status", "next_billing_date"),
    )

    subscription_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    plan_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quotation_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("quotations.id", ondelete="SET NULL"), index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date)
    next_billing_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        enum_type(SubscriptionStatus), default=SubscriptionStatus.DRAFT, nullable=False, index=True
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL")
    )

    customer: Mapped["Customer"] = relationship()
    plan: Mapped["Plan"] = relationship()
    quotation: Mapped[Optional["Quotation"]] = relationship()
    lines: Mapped[list["SubscriptionLine"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )
    status_history: Mapped[list["SubscriptionStatusHistory"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="subscription")


class SubscriptionLine(IdMixin, Base):
    __tablename__ = "subscription_lines"

    subscription_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    variant_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("product_variants.id", ondelete="RESTRICT")
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0.00"), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)

    subscription: Mapped["Subscription"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship()
    variant: Mapped[Optional["ProductVariant"]] = relationship()


class SubscriptionStatusHistory(IdMixin, Base):
    __tablename__ = "subscription_status_history"

    subscription_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[Optional[SubscriptionStatus]] = mapped_column(
        enum_type(SubscriptionStatus)
    )
    to_status: Mapped[SubscriptionStatus] = mapped_column(
        enum_type(SubscriptionStatus), nullable=False
    )
    changed_by: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    subscription: Mapped["Subscription"] = relationship(back_populates="status_history")