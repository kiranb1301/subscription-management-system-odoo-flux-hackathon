from pydantic import BaseModel, EmailStr, Field, field_validator


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 9:
            raise ValueError("Password must be at least 9 characters long")
        if not any(c.isupper() for c in value):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in value):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(not c.isalnum() for c in value):
            raise ValueError("Password must contain at least one special character")
        return value


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class MessageResponse(BaseModel):
    message: str