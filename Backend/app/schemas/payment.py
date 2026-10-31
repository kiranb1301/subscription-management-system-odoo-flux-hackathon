from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import PaymentMethod, PaymentStatus


class AllocationInput(BaseModel):
    invoice_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class PaymentCreate(BaseModel):
    """Pay one invoice with invoice_id, or split a payment with allocations."""

    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: Optional[int] = Field(default=None, gt=0)  # derived from the invoices if omitted
    method: PaymentMethod
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_reference: Optional[str] = Field(default=None, min_length=1, max_length=100)
    payment_date: Optional[datetime] = None
    note: Optional[str] = Field(default=None, max_length=2000)
    invoice_id: Optional[int] = Field(default=None, gt=0)
    allocations: Optional[list[AllocationInput]] = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def _exactly_one_target(self):
        if (self.invoice_id is not None) == bool(self.allocations):
            raise ValueError("Provide either invoice_id or allocations, not both")
        return self


class PaymentAllocationResponse(BaseModel):
    invoice_id: int
    invoice_number: str
    allocated_amount: Decimal
    allocated_at: datetime


class PaymentResponse(BaseModel):
    id: int
    payment_reference: str
    customer_id: int
    customer_name: str
    method: PaymentMethod
    amount: Decimal
    payment_date: datetime
    status: PaymentStatus
    note: Optional[str] = None  # hidden from customers
    available_actions: list[str]
    allocations: list[PaymentAllocationResponse]