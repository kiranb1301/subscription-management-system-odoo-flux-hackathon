from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BillingJobStatus, InvoiceStatus


class GenerateInvoiceRequest(BaseModel):
    subscription_id: int = Field(gt=0)


class InvoiceUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    due_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=5000)


class ApplyDiscountRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=50)


class BillingRunRequest(BaseModel):
    run_date: Optional[date] = None  # defaults to today, cannot be in the future


class InvoiceLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    description: str
    quantity: int
    unit_price: Decimal
    discount_amount: Decimal
    tax_name: Optional[str] = None
    tax_rate: Decimal
    tax_amount: Decimal
    line_total: Decimal


class InvoiceResponse(BaseModel):
    id: int
    invoice_number: str
    subscription_id: int
    subscription_number: str
    customer_id: int
    customer_name: str
    invoice_date: date
    due_date: date
    billing_period_start: date
    billing_period_end: date
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    balance_due: Decimal
    status: InvoiceStatus
    discount_code: Optional[str] = None
    notes: Optional[str] = None  # hidden from customers
    available_actions: list[str]
    lines: list[InvoiceLineResponse]


class InvoiceHistoryResponse(BaseModel):
    from_status: Optional[InvoiceStatus] = None
    to_status: InvoiceStatus
    reason: Optional[str] = None
    changed_at: datetime
    changed_by: Optional[int] = None  # hidden from customers


class BillingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    run_date: date
    status: BillingJobStatus
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    subscriptions_processed: int
    invoices_created: int
    error_message: Optional[str] = None