import re
from datetime import timedelta

from sqlalchemy import update

from app.db.base import utcnow
from app.models import EmailVerificationToken, PasswordResetToken
from app.services import email_service

PASSWORD = "Strong#Pass1"
NEW_PASSWORD = "Brand#New99"
API = "/api/v1"


def register(api, email):
    res = api.post(
        f"{API}/auth/register",
        json={"full_name": email.split("@")[0], "email": email, "password": PASSWORD},
    )
    assert res.status_code == 201, res.text
    return res.json()


def login(api, email, password=PASSWORD):
    return api.post(f"{API}/auth/login", json={"email": email, "password": password})


def auth(api, email):
    res = login(api, email)
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def token_for(email, subject_part):
    for mail in reversed(email_service.outbox):
        if mail["to"] == email and subject_part in mail["subject"]:
            match = re.search(r"token=([\w-]+)", mail["body"])
            assert match, mail["body"]
            return match.group(1)
    raise AssertionError(f"no '{subject_part}' email for {email}")


def mails_to(email):
    return [m for m in email_service.outbox if m["to"] == email]


def expire_all(session_factory, model, column):
    with session_factory() as db:
        db.execute(update(model).values(**{column: utcnow() - timedelta(hours=1)}))
        db.commit()


def test_verify_email_flow(api):
    user = register(api, "kim@example.com")
    assert user["is_email_verified"] is False
    headers = auth(api, "kim@example.com")  # unverified users can still log in
    assert api.get(f"{API}/auth/me", headers=headers).json()["is_email_verified"] is False

    token = token_for("kim@example.com", "Verify")
    assert api.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 200
    assert api.get(f"{API}/auth/me", headers=headers).json()["is_email_verified"] is True

    assert api.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 400  # reuse
    assert api.post(f"{API}/auth/verify-email", json={"token": "x" * 40}).status_code == 400
    assert api.post(f"{API}/auth/verify-email", json={}).status_code == 422


def test_verification_link_expires(api, session_factory):
    register(api, "lee@example.com")
    token = token_for("lee@example.com", "Verify")
    expire_all(session_factory, EmailVerificationToken, "expires_at")
    assert api.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 400
    assert api.get(f"{API}/auth/me", headers=auth(api, "lee@example.com")).json()["is_email_verified"] is False


def test_resend_verification(api):
    assert api.post(f"{API}/auth/resend-verification").status_code == 401
    register(api, "mia@example.com")
    headers = auth(api, "mia@example.com")
    first = token_for("mia@example.com", "Verify")

    assert api.post(f"{API}/auth/resend-verification", headers=headers).status_code == 200
    second = token_for("mia@example.com", "Verify")
    assert first != second and len(mails_to("mia@example.com")) == 2
    assert api.post(f"{API}/auth/verify-email", json={"token": first}).status_code == 400  # replaced
    assert api.post(f"{API}/auth/verify-email", json={"token": second}).status_code == 200
    assert api.post(f"{API}/auth/resend-verification", headers=headers).status_code == 400  # already verified


def test_forgot_password_never_reveals_accounts(api):
    register(api, "ned@example.com")
    email_service.outbox.clear()

    unknown = api.post(f"{API}/auth/forgot-password", json={"email": "ghost@example.com"})
    known = api.post(f"{API}/auth/forgot-password", json={"email": "ned@example.com"})
    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()
    assert mails_to("ghost@example.com") == []
    assert len(mails_to("ned@example.com")) == 1
    assert api.post(f"{API}/auth/forgot-password", json={"email": "not-an-email"}).status_code == 422


def test_reset_password_flow(api):
    register(api, "ola@example.com")
    api.post(f"{API}/auth/forgot-password", json={"email": "ola@example.com"})
    token = token_for("ola@example.com", "Reset")
    url = f"{API}/auth/reset-password"

    assert api.post(url, json={"token": token, "new_password": "short"}).status_code == 422
    assert login(api, "ola@example.com").status_code == 200  # a rejected reset changes nothing

    assert api.post(url, json={"token": token, "new_password": NEW_PASSWORD}).status_code == 200
    assert login(api, "ola@example.com").status_code == 401
    assert login(api, "ola@example.com", NEW_PASSWORD).status_code == 200
    assert api.post(url, json={"token": token, "new_password": "Another#Pass2"}).status_code == 400  # reuse
    assert api.post(url, json={"token": "y" * 40, "new_password": NEW_PASSWORD}).status_code == 400


def test_reset_token_expiry_and_replacement(api, session_factory):
    register(api, "pat@example.com")
    url = f"{API}/auth/reset-password"

    api.post(f"{API}/auth/forgot-password", json={"email": "pat@example.com"})
    first = token_for("pat@example.com", "Reset")
    api.post(f"{API}/auth/forgot-password", json={"email": "pat@example.com"})
    second = token_for("pat@example.com", "Reset")
    assert first != second
    assert api.post(url, json={"token": first, "new_password": NEW_PASSWORD}).status_code == 400  # replaced

    expire_all(session_factory, PasswordResetToken, "expires_at")
    assert api.post(url, json={"token": second, "new_password": NEW_PASSWORD}).status_code == 400  # expired
    assert login(api, "pat@example.com").status_code == 200  # password unchanged