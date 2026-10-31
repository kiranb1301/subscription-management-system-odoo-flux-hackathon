from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: Optional[str] = None
    company_name: Optional[str] = None
    tax_id: Optional[str] = None
    is_active: bool


class CustomerSelfUpdate(BaseModel):
    """Fields a customer may change on their own profile."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=30)
    company_name: Optional[str] = Field(default=None, max_length=200)


class CustomerStaffUpdate(CustomerSelfUpdate):
    """Staff can additionally change tax id and active flag."""

    tax_id: Optional[str] = Field(default=None, max_length=50)
    is_active: Optional[bool] = None