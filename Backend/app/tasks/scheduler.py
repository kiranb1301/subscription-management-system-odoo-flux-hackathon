import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import roles
from app.db.session import get_db
from app.models import Role, User
from app.services.invoice_service import run_billing
from app.services.notification_service import send_overdue_reminders
from app.settings import settings

logger = logging.getLogger(__name__)


def run_daily_jobs(db: Session) -> dict:
    """Bill due subscriptions, then remind customers about overdue invoices."""
    result = {"billing_status": "SKIPPED", "invoices_created": 0, "reminders": 0}

    admin = db.scalar(
        select(User)
        .join(Role, Role.id == User.role_id)
        .where(Role.name == roles.ADMIN, User.is_deleted.is_(False), User.is_active.is_(True))
        .order_by(User.id)
    )
    if admin is None:
        logger.warning("Daily billing skipped: no active admin user exists")
    else:
        try:
            job = run_billing(db, admin)
            result["billing_status"] = job.status.value
            result["invoices_created"] = job.invoices_created
        except Exception:
            db.rollback()
            result["billing_status"] = "FAILED"
            logger.exception("Daily billing run failed")

    try:
        result["reminders"] = send_overdue_reminders(db)
    except Exception:
        db.rollback()
        logger.exception("Overdue reminders failed")

    logger.info("Daily jobs finished: %s", result)
    return result


def _daily_job() -> None:
    gen = get_db()
    db = next(gen)
    try:
        run_daily_jobs(db)
    finally:
        gen.close()


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.SCHEDULER_TIMEZONE)
    scheduler.add_job(
        _daily_job,
        CronTrigger(
            hour=settings.SCHEDULER_HOUR,
            minute=settings.SCHEDULER_MINUTE,
            timezone=settings.SCHEDULER_TIMEZONE,
        ),
        id="daily-billing",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    return scheduler