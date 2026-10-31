from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.account import (
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services import account_service, auth_service
from app.settings import settings

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    user = auth_service.register_customer(db, payload)
    account_service.send_verification(db, user)
    return UserResponse.from_user(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, payload.email, payload.password)
    return TokenResponse(
        access_token=auth_service.issue_token(user),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserResponse.from_user(current_user)


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    account_service.request_password_reset(db, payload.email)
    return MessageResponse(message="If that email is registered, a reset link has been sent")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    account_service.reset_password(db, payload.token, payload.new_password)
    return MessageResponse(message="Password has been reset. You can now log in")


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    account_service.verify_email(db, payload.token)
    return MessageResponse(message="Email verified")


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    account_service.resend_verification(db, current_user)
    return MessageResponse(message="Verification email sent")