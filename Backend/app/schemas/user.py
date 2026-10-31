from typing import Literal

from pydantic import BaseModel

from app.schemas.auth import RegisterRequest


class StaffCreateRequest(RegisterRequest):
    """Same name, email and password rules as registration, plus a staff role."""

    role: Literal["ADMIN", "INTERNAL"]


class UserActiveUpdate(BaseModel):
    is_active: bool


class UserAdminResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    is_active: bool
    is_email_verified: bool

    @classmethod
    def from_user(cls, user) -> "UserAdminResponse":
        return cls(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            role=user.role.name,
            is_active=user.is_active,
            is_email_verified=user.is_email_verified,
        )