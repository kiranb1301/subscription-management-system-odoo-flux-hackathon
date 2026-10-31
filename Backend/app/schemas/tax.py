from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TaxCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    rate: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    is_active: bool = True


class TaxUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    rate: Optional[Decimal] = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    is_active: Optional[bool] = None


class TaxResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rate: Decimal
    is_active: bool