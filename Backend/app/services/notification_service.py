from datetime import timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.base import utcnow
from app.models import Customer, Invoice, Notification, User
from app.models.enums import InvoiceStatus as I
from app.models.enums import NotificationChannel, NotificationStatus as N
from app.services.access import get_customer_id_for_user


def notify(
    db: Session,
    customer_id: int,
    title: str,
    message: str,
    related_type: str | None = None,
    related_id: int | None = None,
) -> None:
    """Queue an in-app notification in the caller's transaction (the caller commits)."""
    customer = db.get(Customer, customer_id)
    db.add(
        Notification(
            user_id=customer.user_id if customer is not None else None,
            customer_id=customer_id,
            channel=NotificationChannel.IN_APP,
            title=title[:200],
            message=message,
            status=N.SENT,
            related_type=related_type,
            related_id=related_id,
            sent_at=utcnow(),
        )
    )


def _scope(db: Session, user: User):
    conditions = [Notification.user_id == user.id]
    own_id = get_customer_id_for_user(db, user)
    if own_id is not None:
        conditions.append(Notification.customer_id == own_id)
    return or_(*conditions)


def list_notifications(
    db: Session, user: User, offset: int, limit: int, unread_only: bool
) -> tuple[list[Notification], int]:
    query = select(Notification).where(_scope(db, user))
    if unread_only:
        query = query.where(Notification.status != N.READ)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Notification.id.desc()).offset(offset).limit(limit)).all()
    return list(items), total


def unread_count(db: Session, user: User) -> int:
    return db.scalar(
        select(func.count()).select_from(Notification).where(_scope(db, user), Notification.status != N.READ)
    ) or 0


def mark_read(db: Session, user: User, notification_id: int) -> Notification:
    note = db.scalar(select(Notification).where(Notification.id == notification_id, _scope(db, user)))
    if note is None:
        raise NotFoundError("Notification not found")
    if note.status != N.READ:
        note.status = N.READ
        note.read_at = utcnow()
        db.commit()
        db.refresh(note)
    return note


def mark_all_read(db: Session, user: User) -> int:
    ids = list(
        db.scalars(select(Notification.id).where(_scope(db, user), Notification.status != N.READ)).all()
    )
    if ids:
        db.execute(
            update(Notification)
            .where(Notification.id.in_(ids))
            .values(status=N.READ, read_at=utcnow())
        )
        db.commit()
    return len(ids)


def send_overdue_reminders(db: Session) -> int:
    from app.services.invoice_service import mark_overdue

    mark_overdue(db)
    cutoff = utcnow() - timedelta(hours=24)
    recent = set(
        db.scalars(
            select(Notification.related_id).where(
                Notification.related_type == "invoice_overdue", Notification.created_at >= cutoff
            )
        ).all()
    )
    created = 0
    for inv in db.scalars(
        select(Invoice).where(Invoice.is_deleted.is_(False), Invoice.status == I.OVERDUE)
    ).all():
        if inv.id in recent:
            continue
        notify(
            db, inv.customer_id, "Payment reminder",
            f"Invoice {inv.invoice_number} is overdue. Balance due: {inv.total_amount - inv.paid_amount}.",
            "invoice_overdue", inv.id,
        )
        created += 1
    if created:
        db.commit()
    return created