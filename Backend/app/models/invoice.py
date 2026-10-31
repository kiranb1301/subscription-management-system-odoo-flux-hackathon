from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
from app.models.enums import InvoiceStatus

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.payment import PaymentAllocation
    from app.models.subscription import Subscription
    
    

class Invoice(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_status_due_date", "status", "due_date"),
        UniqueConstraint(
            "subscription_id",
            "billing_period_start",
            "billing_period_end",
            name="uq_subscription_billing_period",
        ),
    )

    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    subscription_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    billing_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    billing_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        enum_type(InvoiceStatus), default=InvoiceStatus.DRAFT, nullable=False, index=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    subscription: Mapped["Subscription"] = relationship(back_populates="invoices")
    customer: Mapped["Customer"] = relationship()
    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    status_history: Mapped[list["InvoiceStatusHistory"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    allocations: Mapped[list["PaymentAllocation"]] = relationship(back_populates="invoice")

    @property
    def balance_due(self) -> Decimal:
        return self.total_amount - self.paid_amount


class InvoiceLine(IdMixin, Base):
    """Price, tax and discount are SNAPSHOTS. Never recalculate from the product."""

    __tablename__ = "invoice_lines"

    invoice_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    variant_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("product_variants.id", ondelete="SET NULL")
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    tax_name: Mapped[Optional[str]] = mapped_column(String(100))
    tax_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0.00"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)

    invoice: Mapped["Invoice"] = relationship(back_populates="lines")


class InvoiceStatusHistory(IdMixin, Base):
    __tablename__ = "invoice_status_history"

    invoice_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[Optional[InvoiceStatus]] = mapped_column(enum_type(InvoiceStatus))
    to_status: Mapped[InvoiceStatus] = mapped_column(enum_type(InvoiceStatus), nullable=False)
    changed_by: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    invoice: Mapped["Invoice"] = relationship(back_populates="status_history")