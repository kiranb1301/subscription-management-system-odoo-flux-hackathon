from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigInt, IdMixin, Money, TimestampMixin, enum_type, utcnow
from app.models.enums import PaymentMethod, PaymentStatus

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.invoice import Invoice
    

class Payment(IdMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    payment_reference: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    method: Mapped[PaymentMethod] = mapped_column(enum_type(PaymentMethod), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    payment_date: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[PaymentStatus] = mapped_column(
        enum_type(PaymentStatus), default=PaymentStatus.PENDING, nullable=False, index=True
    )

    customer: Mapped["Customer"] = relationship()
    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )


class PaymentAllocation(IdMixin, Base):
    """One payment can cover many invoices, and one invoice can be paid in parts."""

    __tablename__ = "payment_allocations"
    __table_args__ = (UniqueConstraint("payment_id", "invoice_id"),)

    payment_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    allocated_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    allocated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    payment: Mapped["Payment"] = relationship(back_populates="allocations")
    invoice: Mapped["Invoice"] = relationship(back_populates="allocations")