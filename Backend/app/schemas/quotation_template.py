from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TemplateLineIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    product_id: int = Field(gt=0)
    variant_id: Optional[int] = Field(default=None, gt=0)
    description: Optional[str] = Field(default=None, max_length=255)
    quantity: int = Field(default=1, ge=1, le=100000)


class TemplateCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=150)
    plan_id: Optional[int] = Field(default=None, gt=0)
    validity_days: int = Field(default=30, ge=1, le=365)
    description: Optional[str] = Field(default=None, max_length=5000)
    is_active: bool = True
    lines: list[TemplateLineIn] = Field(default_factory=list)


class TemplateUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    plan_id: Optional[int] = Field(default=None, gt=0)
    validity_days: Optional[int] = Field(default=None, ge=1, le=365)
    description: Optional[str] = Field(default=None, max_length=5000)
    is_active: Optional[bool] = None
    # When provided, replaces all template lines
    lines: Optional[list[TemplateLineIn]] = None


class TemplateLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    variant_id: Optional[int] = None
    description: Optional[str] = None
    quantity: int


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    plan_id: Optional[int] = None
    validity_days: int
    description: Optional[str] = None
    is_active: bool
    lines: list[TemplateLineResponse]