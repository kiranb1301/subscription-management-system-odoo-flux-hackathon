from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import QuotationStatus
from app.schemas.product import Price


class QuotationLineIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    product_id: int = Field(gt=0)
    variant_id: Optional[int] = Field(default=None, gt=0)
    description: Optional[str] = Field(default=None, max_length=255)
    quantity: int = Field(default=1, ge=1, le=100000)
    unit_price: Optional[Price] = None  # None = plan override or catalog price
    discount_amount: Price = Decimal("0.00")  # fixed amount for the whole line


class QuotationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: int = Field(gt=0)
    plan_id: Optional[int] = Field(default=None, gt=0)  # defaults to the template's plan
    template_id: Optional[int] = Field(default=None, gt=0)
    valid_until: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=5000)
    lines: list[QuotationLineIn] = Field(default_factory=list)  # empty = copy from template


class QuotationUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    valid_until: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=5000)
    # When provided, replaces all lines and reprices them
    lines: Optional[list[QuotationLineIn]] = None


class QuotationLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    variant_id: Optional[int] = None
    description: str
    quantity: int
    unit_price: Decimal
    discount_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    line_total: Decimal


class QuotationResponse(BaseModel):
    id: int
    quotation_number: str
    customer_id: int
    customer_name: str
    plan_id: int
    plan_name: str
    template_id: Optional[int] = None
    status: QuotationStatus
    quotation_date: date
    valid_until: Optional[date] = None
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    notes: Optional[str] = None  # hidden from customers
    lines: list[QuotationLineResponse]

    @classmethod
    def from_quotation(cls, q, staff: bool) -> "QuotationResponse":
        return cls(
            id=q.id,
            quotation_number=q.quotation_number,
            customer_id=q.customer_id,
            customer_name=q.customer.name,
            plan_id=q.plan_id,
            plan_name=q.plan.name,
            template_id=q.template_id,
            status=q.status,
            quotation_date=q.quotation_date,
            valid_until=q.valid_until,
            subtotal=q.subtotal,
            discount_amount=q.discount_amount,
            tax_amount=q.tax_amount,
            total_amount=q.total_amount,
            notes=q.notes if staff else None,
            lines=[
                QuotationLineResponse.model_validate(line)
                for line in sorted(q.lines, key=lambda x: x.id)
            ],
        )