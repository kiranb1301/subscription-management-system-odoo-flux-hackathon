import calendar
from datetime import date, timedelta

from app.models.enums import BillingInterval


def add_months(d: date, months: int) -> date:
    index = d.month - 1 + months
    year = d.year + index // 12
    month = index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def advance_date(d: date, interval: BillingInterval, count: int) -> date:
    """Move a date forward by `count` billing intervals (month ends are clamped)."""
    if interval == BillingInterval.DAILY:
        return d + timedelta(days=count)
    if interval == BillingInterval.WEEKLY:
        return d + timedelta(weeks=count)
    if interval == BillingInterval.MONTHLY:
        return add_months(d, count)
    if interval == BillingInterval.YEARLY:
        return add_months(d, 12 * count)
    raise ValueError(f"Unsupported billing interval: {interval}")