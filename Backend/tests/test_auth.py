import pytest

VALID = {"full_name": "Asha Rao", "email": "asha@example.com", "password": "Strong#Pass1"}


def test_register_success(api):
    res = api.post("/api/v1/auth/register", json=VALID)
    assert res.status_code == 201
    body = res.json()
    assert body["email"] == "asha@example.com"
    assert body["role"] == "CUSTOMER"
    assert "password" not in body and "password_hash" not in body


def test_register_duplicate_email(api):
    api.post("/api/v1/auth/register", json=VALID)
    res = api.post("/api/v1/auth/register", json={**VALID, "email": "ASHA@example.com"})
    assert res.status_code == 409


@pytest.mark.parametrize(
    "password",
    ["Short#1a", "alllowercase#1", "ALLUPPERCASE#1", "NoSpecialChar1"],
)
def test_register_weak_password(api, password):
    res = api.post("/api/v1/auth/register", json={**VALID, "password": password})
    assert res.status_code == 422


def test_login_and_me(api):
    api.post("/api/v1/auth/register", json=VALID)
    res = api.post(
        "/api/v1/auth/login", json={"email": VALID["email"], "password": VALID["password"]}
    )
    assert res.status_code == 200
    token = res.json()["access_token"]

    me = api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == VALID["email"]


def test_login_wrong_password(api):
    api.post("/api/v1/auth/register", json=VALID)
    res = api.post(
        "/api/v1/auth/login", json={"email": VALID["email"], "password": "Wrong#Pass9"}
    )
    assert res.status_code == 401


def test_me_requires_token(api):
    assert api.get("/api/v1/auth/me").status_code == 401
    bad = api.get("/api/v1/auth/me", headers={"Authorization": "Bearer nonsense"})
    assert bad.status_code == 401