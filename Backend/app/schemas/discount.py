import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import DiscountType
from app.schemas.product import Price

PositiveAmount = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]
CODE_RE = re.compile(r"[A-Z0-9_-]{3,50}")


def normalize_code(value: str) -> str:
    value = value.strip().upper()
    if not CODE_RE.fullmatch(value):
        raise ValueError("code must be 3-50 characters: letters, digits, '-' or '_'")
    return value


class DiscountCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str
    name: str = Field(min_length=1, max_length=150)
    discount_type: DiscountType = DiscountType.PERCENTAGE
    discount_value: PositiveAmount
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    usage_limit: Optional[int] = Field(default=None, ge=1)
    per_customer_limit: Optional[int] = Field(default=None, ge=1)
    min_purchase_amount: Optional[Price] = None
    min_quantity: Optional[int] = Field(default=None, ge=1)
    is_active: bool = True
    product_ids: list[int] = Field(default_factory=list)  # empty = applies to every product

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        return normalize_code(value)

    @model_validator(mode="after")
    def _check(self):
        if self.discount_type == DiscountType.PERCENTAGE and self.discount_value > 100:
            raise ValueError("A percentage discount cannot exceed 100")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class DiscountUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[PositiveAmount] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    usage_limit: Optional[int] = Field(default=None, ge=1)
    per_customer_limit: Optional[int] = Field(default=None, ge=1)
    min_purchase_amount: Optional[Price] = None
    min_quantity: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None
    # When provided, replaces the product list (an empty list = every product)
    product_ids: Optional[list[int]] = None


class DiscountResponse(BaseModel):
    id: int
    code: str
    name: str
    discount_type: DiscountType
    discount_value: Decimal
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    usage_limit: Optional[int] = None
    per_customer_limit: Optional[int] = None
    min_purchase_amount: Optional[Decimal] = None
    min_quantity: Optional[int] = None
    used_count: int
    is_active: bool
    product_ids: list[int]

    @classmethod
    def from_discount(cls, d) -> "DiscountResponse":
        return cls(
            id=d.id,
            code=d.code,
            name=d.name,
            discount_type=d.discount_type,
            discount_value=d.discount_value,
            start_date=d.start_date,
            end_date=d.end_date,
            usage_limit=d.usage_limit,
            per_customer_limit=d.per_customer_limit,
            min_purchase_amount=d.min_purchase_amount,
            min_quantity=d.min_quantity,
            used_count=d.used_count,
            is_active=d.is_active,
            product_ids=sorted(m.product_id for m in d.product_mappings),
        )