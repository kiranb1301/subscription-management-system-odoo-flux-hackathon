from decimal import Decimal
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProductType
from app.schemas.tax import TaxResponse

Price = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]


class VariantOptionIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    option_name: str = Field(min_length=1, max_length=100)
    option_value: str = Field(min_length=1, max_length=100)


class VariantOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    option_name: str
    option_value: str


class VariantCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    variant_name: str = Field(min_length=1, max_length=100)
    additional_price: Price = Decimal("0.00")
    is_active: bool = True
    options: list[VariantOptionIn] = Field(default_factory=list)


class VariantUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    variant_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    additional_price: Optional[Price] = None
    is_active: Optional[bool] = None
    # When provided, replaces all existing options
    options: Optional[list[VariantOptionIn]] = None


class VariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    variant_name: str
    additional_price: Decimal
    final_price: Decimal
    is_active: bool
    options: list[VariantOptionResponse]


class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    product_type: ProductType = ProductType.SERVICE
    sales_price: Price
    cost_price: Price = Decimal("0.00")
    notes: Optional[str] = Field(default=None, max_length=5000)
    is_active: bool = True
    tax_ids: list[int] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    product_type: Optional[ProductType] = None
    sales_price: Optional[Price] = None
    cost_price: Optional[Price] = None
    notes: Optional[str] = Field(default=None, max_length=5000)
    is_active: Optional[bool] = None
    # When provided, replaces all linked taxes
    tax_ids: Optional[list[int]] = None


class ProductResponse(BaseModel):
    id: int
    name: str
    product_type: ProductType
    sales_price: Decimal
    cost_price: Optional[Decimal] = None  # null for customers
    notes: Optional[str] = None
    is_active: bool
    variants: list[VariantResponse]
    taxes: list[TaxResponse]

    @classmethod
    def from_product(cls, product, staff: bool) -> "ProductResponse":
        variants = sorted(
            (v for v in product.variants if staff or v.is_active), key=lambda v: v.id
        )
        taxes = [
            pt.tax
            for pt in sorted(product.product_taxes, key=lambda x: x.id)
            if staff or pt.tax.is_active
        ]
        return cls(
            id=product.id,
            name=product.name,
            product_type=product.product_type,
            sales_price=product.sales_price,
            cost_price=product.cost_price if staff else None,
            notes=product.notes,
            is_active=product.is_active,
            variants=[VariantResponse.model_validate(v) for v in variants],
            taxes=[TaxResponse.model_validate(t) for t in taxes],
        )