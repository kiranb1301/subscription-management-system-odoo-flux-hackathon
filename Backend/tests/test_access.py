PASSWORD = "Strong#Pass1"


def register(api, email):
    res = api.post(
        "/api/v1/auth/register",
        json={"full_name": email.split("@")[0], "email": email, "password": PASSWORD},
    )
    assert res.status_code == 201
    return res.json()


def login(api, email, password=PASSWORD):
    res = api.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_customer_cannot_read_another_customers_profile(api):
    register(api, "a@example.com")
    register(api, "b@example.com")
    a, b = login(api, "a@example.com"), login(api, "b@example.com")

    b_id = api.get("/api/v1/customers/me", headers=b).json()["id"]
    a_id = api.get("/api/v1/customers/me", headers=a).json()["id"]

    assert api.get(f"/api/v1/customers/{a_id}", headers=a).status_code == 200
    # Same status as a missing record, so IDs cannot be probed
    assert api.get(f"/api/v1/customers/{b_id}", headers=a).status_code == 404
    assert api.get("/api/v1/customers/999999", headers=a).status_code == 404


def test_customer_cannot_use_staff_endpoints(api):
    register(api, "a@example.com")
    a = login(api, "a@example.com")
    assert api.get("/api/v1/customers", headers=a).status_code == 403
    assert api.get("/api/v1/users", headers=a).status_code == 403
    assert (
        api.post(
            "/api/v1/users",
            headers=a,
            json={"full_name": "X", "email": "x@example.com", "password": PASSWORD, "role": "ADMIN"},
        ).status_code
        == 403
    )


def test_customer_can_update_only_allowed_fields(api):
    register(api, "a@example.com")
    a = login(api, "a@example.com")
    res = api.put(
        "/api/v1/customers/me",
        headers=a,
        json={"phone": "9999999999", "tax_id": "HACK", "is_active": False},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["phone"] == "9999999999"
    assert body["tax_id"] is None and body["is_active"] is True


def test_internal_staff_can_manage_customers_but_not_staff(api, make_staff):
    register(api, "a@example.com")
    make_staff("staff@example.com", "INTERNAL")
    staff = login(api, "staff@example.com")

    listing = api.get("/api/v1/customers", headers=staff)
    assert listing.status_code == 200 and listing.json()["total"] == 1
    cid = listing.json()["items"][0]["id"]
    assert api.get(f"/api/v1/customers/{cid}", headers=staff).status_code == 200
    assert api.put(f"/api/v1/customers/{cid}", headers=staff, json={"tax_id": "GST123"}).status_code == 200

    assert api.get("/api/v1/users", headers=staff).status_code == 403
    assert (
        api.post(
            "/api/v1/users",
            headers=staff,
            json={"full_name": "Y", "email": "y@example.com", "password": PASSWORD, "role": "INTERNAL"},
        ).status_code
        == 403
    )


def test_admin_creates_staff_and_deactivates_them(api, make_staff):
    make_staff("admin@example.com", "ADMIN")
    admin = login(api, "admin@example.com")

    created = api.post(
        "/api/v1/users",
        headers=admin,
        json={"full_name": "New Staff", "email": "new@example.com", "password": PASSWORD, "role": "INTERNAL"},
    )
    assert created.status_code == 201 and created.json()["role"] == "INTERNAL"
    staff_id = created.json()["id"]

    weak = api.post(
        "/api/v1/users",
        headers=admin,
        json={"full_name": "W", "email": "w@example.com", "password": "weak", "role": "INTERNAL"},
    )
    assert weak.status_code == 422
    dup = api.post(
        "/api/v1/users",
        headers=admin,
        json={"full_name": "N", "email": "NEW@example.com", "password": PASSWORD, "role": "INTERNAL"},
    )
    assert dup.status_code == 409

    staff = login(api, "new@example.com")
    assert api.get("/api/v1/auth/me", headers=staff).status_code == 200
    off = api.patch(f"/api/v1/users/{staff_id}/active", headers=admin, json={"is_active": False})
    assert off.status_code == 200
    assert api.get("/api/v1/auth/me", headers=staff).status_code == 401

    me = api.get("/api/v1/auth/me", headers=admin).json()
    own = api.patch(f"/api/v1/users/{me['id']}/active", headers=admin, json={"is_active": False})
    assert own.status_code == 400