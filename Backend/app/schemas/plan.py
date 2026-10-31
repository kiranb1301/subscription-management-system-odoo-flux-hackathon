from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import BillingInterval
from app.schemas.product import Price


class PlanProductIn(BaseModel):
    product_id: int = Field(gt=0)
    variant_id: Optional[int] = Field(default=None, gt=0)
    default_quantity: int = Field(default=1, ge=1, le=100000)
    unit_price: Optional[Price] = None  # None = use the product price


class PlanCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=150)
    billing_interval: BillingInterval = BillingInterval.MONTHLY
    interval_count: int = Field(default=1, ge=1, le=120)
    minimum_quantity: int = Field(default=1, ge=1, le=100000)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    auto_close: bool = False
    allow_pause: bool = False
    allow_renewal: bool = True
    allow_early_close: bool = False
    is_active: bool = True
    products: list[PlanProductIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class PlanUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    billing_interval: Optional[BillingInterval] = None
    interval_count: Optional[int] = Field(default=None, ge=1, le=120)
    minimum_quantity: Optional[int] = Field(default=None, ge=1, le=100000)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    auto_close: Optional[bool] = None
    allow_pause: Optional[bool] = None
    allow_renewal: Optional[bool] = None
    allow_early_close: Optional[bool] = None
    is_active: Optional[bool] = None
    # When provided, replaces all product lines of the plan
    products: Optional[list[PlanProductIn]] = None


class PlanProductResponse(BaseModel):
    product_id: int
    product_name: str
    variant_id: Optional[int] = None
    variant_name: Optional[str] = None
    default_quantity: int
    unit_price: Optional[Decimal] = None
    effective_unit_price: Decimal


class PlanResponse(BaseModel):
    id: int
    name: str
    billing_interval: BillingInterval
    interval_count: int
    minimum_quantity: int
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    auto_close: bool
    allow_pause: bool
    allow_renewal: bool
    allow_early_close: bool
    is_active: bool
    products: list[PlanProductResponse]

    @classmethod
    def from_plan(cls, plan, staff: bool) -> "PlanResponse":
        lines = []
        for pp in sorted(plan.plan_products, key=lambda x: x.id):
            product, variant = pp.product, pp.variant
            if not staff:
                if product.is_deleted or not product.is_active:
                    continue
                if variant is not None and not variant.is_active:
                    continue
            if pp.unit_price is not None:
                effective = pp.unit_price
            else:
                extra = variant.additional_price if variant is not None else Decimal("0.00")
                effective = product.sales_price + extra
            lines.append(
                PlanProductResponse(
                    product_id=product.id,
                    product_name=product.name,
                    variant_id=pp.variant_id,
                    variant_name=variant.variant_name if variant is not None else None,
                    default_quantity=pp.default_quantity,
                    unit_price=pp.unit_price,
                    effective_unit_price=effective,
                )
            )
        return cls(
            id=plan.id,
            name=plan.name,
            billing_interval=plan.billing_interval,
            interval_count=plan.interval_count,
            minimum_quantity=plan.minimum_quantity,
            start_date=plan.start_date,
            end_date=plan.end_date,
            auto_close=plan.auto_close,
            allow_pause=plan.allow_pause,
            allow_renewal=plan.allow_renewal,
            allow_early_close=plan.allow_early_close,
            is_active=plan.is_active,
            products=lines,
        )