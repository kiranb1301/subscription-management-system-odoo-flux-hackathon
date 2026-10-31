from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
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
)
from app.models.enums import QuotationStatus


class QuotationTemplate(IdMixin, TimestampMixin, Base):
    __tablename__ = "quotation_templates"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    plan_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("plans.id", ondelete="SET NULL"), index=True
    )
    validity_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    plan: Mapped[Optional["Plan"]] = relationship()
    lines: Mapped[list["QuotationTemplateLine"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class QuotationTemplateLine(IdMixin, Base):
    __tablename__ = "quotation_template_lines"

    template_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("quotation_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    variant_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("product_variants.id", ondelete="RESTRICT"), index=True
    )
    description: Mapped[Optional[str]] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    template: Mapped["QuotationTemplate"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship()
    variant: Mapped[Optional["ProductVariant"]] = relationship()


class Quotation(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "quotations"

    quotation_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    plan_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    template_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("quotation_templates.id", ondelete="SET NULL")
    )
    status: Mapped[QuotationStatus] = mapped_column(
        enum_type(QuotationStatus), default=QuotationStatus.DRAFT, nullable=False, index=True
    )
    quotation_date: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[Optional[date]] = mapped_column(Date)
    subtotal: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL")
    )

    customer: Mapped["Customer"] = relationship()
    plan: Mapped["Plan"] = relationship()
    template: Mapped[Optional["QuotationTemplate"]] = relationship()
    lines: Mapped[list["QuotationLine"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan"
    )


class QuotationLine(IdMixin, Base):
    __tablename__ = "quotation_lines"

    quotation_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False, index=True
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
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)

    quotation: Mapped["Quotation"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship()
    variant: Mapped[Optional["ProductVariant"]] = relationship()