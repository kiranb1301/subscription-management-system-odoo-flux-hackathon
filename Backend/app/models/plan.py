from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigInt, IdMixin, Money, Rate, TimestampMixin, enum_type
from app.models.enums import BillingInterval


class Plan(IdMixin, TimestampMixin, Base):
    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    billing_interval: Mapped[BillingInterval] = mapped_column(
        enum_type(BillingInterval, 20), default=BillingInterval.MONTHLY, nullable=False
    )
    interval_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    minimum_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    auto_close: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_pause: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_renewal: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_early_close: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    plan_products: Mapped[list["PlanProduct"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class PlanProduct(IdMixin, Base):
    __tablename__ = "plan_products"
    __table_args__ = (UniqueConstraint("plan_id", "product_id", "variant_id"),)

    plan_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    variant_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("product_variants.id", ondelete="RESTRICT"), index=True
    )
    default_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Optional price override for this plan; NULL means use the product price
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Money)

    plan: Mapped["Plan"] = relationship(back_populates="plan_products")
    product: Mapped["Product"] = relationship()
    variant: Mapped[Optional["ProductVariant"]] = relationship()


class Tax(IdMixin, TimestampMixin, Base):
    __tablename__ = "taxes"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Rate, nullable=False)  # percent, e.g. 18.00
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProductTax(IdMixin, Base):
    __tablename__ = "product_taxes"
    __table_args__ = (UniqueConstraint("product_id", "tax_id"),)

    product_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tax_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("taxes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    product: Mapped["Product"] = relationship(back_populates="product_taxes")
    tax: Mapped["Tax"] = relationship()