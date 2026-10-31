from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BillingInterval, SubscriptionStatus


class SubscriptionCreate(BaseModel):
    quotation_id: int = Field(gt=0)
    payment_terms_days: int = Field(default=0, ge=0, le=365)


class ActivateRequest(BaseModel):
    start_date: Optional[date] = None


class ReasonRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reason: Optional[str] = Field(default=None, max_length=200)


class RenewRequest(BaseModel):
    periods: int = Field(default=1, ge=1, le=60)


class SubscriptionLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    variant_id: Optional[int] = None
    description: str
    quantity: int
    unit_price: Decimal
    discount_amount: Decimal
    tax_rate: Decimal
    line_total: Decimal


class SubscriptionResponse(BaseModel):
    id: int
    subscription_number: str
    customer_id: int
    customer_name: str
    plan_id: int
    plan_name: str
    billing_interval: BillingInterval
    interval_count: int
    quotation_id: Optional[int] = None
    status: SubscriptionStatus
    start_date: date
    expiry_date: Optional[date] = None
    next_billing_date: Optional[date] = None
    payment_terms_days: int
    pending_request: Optional[str] = None  # "CANCEL" or "RENEW"
    available_actions: list[str]
    lines: list[SubscriptionLineResponse]


class HistoryResponse(BaseModel):
    from_status: Optional[SubscriptionStatus] = None
    to_status: SubscriptionStatus
    reason: Optional[str] = None
    changed_at: datetime
    changed_by: Optional[int] = None  # hidden from customers