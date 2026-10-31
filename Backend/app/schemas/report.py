from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class SummaryResponse(BaseModel):
    mrr: Decimal
    arr: Decimal
    active_subscriptions: int
    subscriptions_by_status: dict[str, int]
    revenue_collected: Decimal
    refunded_total: Decimal
    outstanding_amount: Decimal
    outstanding_count: int
    overdue_amount: Decimal
    overdue_count: int
    invoices_by_status: dict[str, int]


class RevenuePoint(BaseModel):
    period: str
    amount: Decimal
    payments: int


class RevenueResponse(BaseModel):
    group_by: str
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    total_collected: Decimal
    total_refunded: Decimal
    points: list[RevenuePoint]


class OverdueInvoiceResponse(BaseModel):
    invoice_id: int
    invoice_number: str
    customer_id: int
    customer_name: str
    due_date: date
    days_overdue: int
    total_amount: Decimal
    paid_amount: Decimal
    balance_due: Decimal