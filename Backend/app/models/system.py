from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigInt, CreatedAtMixin, IdMixin, enum_type
from app.models.enums import BillingJobStatus, NotificationChannel, NotificationStatus


class Notification(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        enum_type(NotificationChannel, 20), default=NotificationChannel.EMAIL, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        enum_type(NotificationStatus, 20), default=NotificationStatus.PENDING, nullable=False, index=True
    )
    related_type: Mapped[Optional[str]] = mapped_column(String(50))
    related_id: Mapped[Optional[int]] = mapped_column(BigInt)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    user: Mapped[Optional["User"]] = relationship()
    customer: Mapped[Optional["Customer"]] = relationship()


class BillingJob(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "billing_jobs"

    job_type: Mapped[str] = mapped_column(String(50), default="GENERATE_INVOICES", nullable=False)
    run_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[BillingJobStatus] = mapped_column(
        enum_type(BillingJobStatus, 20), default=BillingJobStatus.PENDING, nullable=False, index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    subscriptions_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invoices_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)


class AuditLog(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id"),)

    user_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(BigInt)
    old_values: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    new_values: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))

    user: Mapped[Optional["User"]] = relationship()