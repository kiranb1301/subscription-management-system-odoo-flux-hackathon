from datetime import date, timedelta
from decimal import Decimal

import pytest

PASSWORD = "Strong#Pass1"
API = "/api/v1"


def _login(api, email):
    res = api.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture()
def users(api, make_staff):
    make_staff("admin@example.com", "ADMIN")
    make_staff("staff@example.com", "INTERNAL")
    res = api.post(
        f"{API}/auth/register",
        json={"full_name": "Cust", "email": "cust@example.com", "password": PASSWORD},
    )
    assert res.status_code == 201
    return {
        "admin": _login(api, "admin@example.com"),
        "staff": _login(api, "staff@example.com"),
        "customer": _login(api, "cust@example.com"),
    }


def make_product(api, headers, **over):
    body = {"name": "Cloud Storage", "sales_price": "100.00", "cost_price": "40.00", **over}
    res = api.post(f"{API}/products", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def make_plan(api, headers, **over):
    body = {"name": "Monthly Basic", **over}
    res = api.post(f"{API}/plans", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_only_admin_can_write_catalog(api, users):
    assert api.post(f"{API}/products", json={"name": "X", "sales_price": "10"}).status_code == 401

    for who in ("customer", "staff"):
        h = users[who]
        assert api.post(f"{API}/products", headers=h, json={"name": "X", "sales_price": "10"}).status_code == 403
        assert api.post(f"{API}/taxes", headers=h, json={"name": "GST", "rate": "18"}).status_code == 403
        assert api.post(f"{API}/plans", headers=h, json={"name": "P"}).status_code == 403

    assert api.post(f"{API}/products", headers=users["admin"], json={"name": "X", "sales_price": "10"}).status_code == 201


def test_product_validation(api, users):
    admin = users["admin"]
    bad_bodies = [
        {"name": "X", "sales_price": "-1"},
        {"name": "X", "sales_price": "10", "cost_price": "-5"},
        {"sales_price": "10"},
        {"name": "   ", "sales_price": "10"},
        {"name": "X", "sales_price": "10.999"},
    ]
    for body in bad_bodies:
        assert api.post(f"{API}/products", headers=admin, json=body).status_code == 422, body

    unknown_tax = api.post(
        f"{API}/products", headers=admin, json={"name": "X", "sales_price": "10", "tax_ids": [999]}
    )
    assert unknown_tax.status_code == 400


def test_customers_see_only_active_products_and_no_cost_price(api, users):
    admin, staff, customer = users["admin"], users["staff"], users["customer"]
    active = make_product(api, admin, name="Active")
    inactive = make_product(api, admin, name="Hidden", is_active=False)

    cust_list = api.get(f"{API}/products", headers=customer).json()
    assert cust_list["total"] == 1
    assert cust_list["items"][0]["id"] == active["id"]
    assert cust_list["items"][0]["cost_price"] is None

    staff_list = api.get(f"{API}/products", headers=staff).json()
    assert staff_list["total"] == 2
    by_id = {p["id"]: p for p in staff_list["items"]}
    assert Decimal(by_id[active["id"]]["cost_price"]) == Decimal("40.00")

    assert api.get(f"{API}/products/{inactive['id']}", headers=customer).status_code == 404
    assert api.get(f"{API}/products/{inactive['id']}", headers=staff).status_code == 200

    page = api.get(f"{API}/products?page=1&page_size=1", headers=staff).json()
    assert len(page["items"]) == 1 and page["total"] == 2


def test_variants_and_final_price(api, users):
    admin, customer = users["admin"], users["customer"]
    product = make_product(api, admin)
    url = f"{API}/products/{product['id']}/variants"

    created = api.post(
        url,
        headers=admin,
        json={"variant_name": "Pro", "additional_price": "25.50",
              "options": [{"option_name": "Seats", "option_value": "10"}]},
    )
    assert created.status_code == 201
    variant = created.json()
    assert Decimal(variant["final_price"]) == Decimal("125.50")
    assert variant["options"][0]["option_value"] == "10"

    # duplicate name (case-insensitive) is rejected
    dup = api.post(url, headers=admin, json={"variant_name": "PRO"})
    assert dup.status_code == 409

    # customers see it while active, not after deactivation
    seen = api.get(f"{API}/products/{product['id']}", headers=customer).json()
    assert len(seen["variants"]) == 1
    assert api.delete(f"{url}/{variant['id']}", headers=admin).status_code == 204
    seen = api.get(f"{API}/products/{product['id']}", headers=customer).json()
    assert seen["variants"] == []
    staff_seen = api.get(f"{API}/products/{product['id']}", headers=admin).json()
    assert len(staff_seen["variants"]) == 1 and staff_seen["variants"][0]["is_active"] is False

    # options are replaced on update
    upd = api.put(
        f"{url}/{variant['id']}",
        headers=admin,
        json={"options": [{"option_name": "Seats", "option_value": "20"}]},
    )
    assert upd.status_code == 200 and len(upd.json()["options"]) == 1
    assert upd.json()["options"][0]["option_value"] == "20"


def test_tax_rules(api, users):
    admin, staff, customer = users["admin"], users["staff"], users["customer"]

    assert api.post(f"{API}/taxes", headers=admin, json={"name": "GST", "rate": "150"}).status_code == 422
    assert api.post(f"{API}/taxes", headers=admin, json={"name": "GST", "rate": "-1"}).status_code == 422

    created = api.post(f"{API}/taxes", headers=admin, json={"name": "GST", "rate": "18"})
    assert created.status_code == 201
    tax = created.json()
    assert Decimal(tax["rate"]) == Decimal("18")
    assert api.post(f"{API}/taxes", headers=admin, json={"name": "gst", "rate": "5"}).status_code == 409

    assert api.get(f"{API}/taxes", headers=staff).status_code == 200
    assert api.get(f"{API}/taxes", headers=customer).status_code == 403

    product = make_product(api, admin, tax_ids=[tax["id"]])
    assert len(product["taxes"]) == 1
    seen = api.get(f"{API}/products/{product['id']}", headers=customer).json()
    assert Decimal(seen["taxes"][0]["rate"]) == Decimal("18")

    # a deactivated tax disappears from the customer view
    assert api.delete(f"{API}/taxes/{tax['id']}", headers=admin).status_code == 204
    seen = api.get(f"{API}/products/{product['id']}", headers=customer).json()
    assert seen["taxes"] == []


def test_plan_visibility_for_customers(api, users):
    admin, staff, customer = users["admin"], users["staff"], users["customer"]
    today = date.today()

    make_plan(api, admin, name="Open")
    make_plan(api, admin, name="Inactive", is_active=False)
    expired = make_plan(
        api, admin, name="Expired",
        start_date=(today - timedelta(days=10)).isoformat(),
        end_date=(today - timedelta(days=1)).isoformat(),
    )
    make_plan(api, admin, name="Future", start_date=(today + timedelta(days=1)).isoformat())

    cust = api.get(f"{API}/plans", headers=customer).json()
    assert cust["total"] == 1 and cust["items"][0]["name"] == "Open"

    assert api.get(f"{API}/plans", headers=staff).json()["total"] == 4
    assert api.get(f"{API}/plans?is_active=false", headers=staff).json()["total"] == 1

    assert api.get(f"{API}/plans/{expired['id']}", headers=customer).status_code == 404
    assert api.get(f"{API}/plans/{expired['id']}", headers=staff).status_code == 200


def test_plan_validation(api, users):
    admin = users["admin"]
    p1 = make_product(api, admin, name="One")
    p2 = make_product(api, admin, name="Two")
    other_variant = api.post(
        f"{API}/products/{p2['id']}/variants", headers=admin, json={"variant_name": "V"}
    ).json()
    today = date.today()

    assert api.post(f"{API}/plans", headers=admin, json={"name": "P", "interval_count": 0}).status_code == 422
    assert api.post(f"{API}/plans", headers=admin, json={"name": "P", "minimum_quantity": 0}).status_code == 422
    assert api.post(
        f"{API}/plans", headers=admin,
        json={"name": "P", "start_date": today.isoformat(),
              "end_date": (today - timedelta(days=1)).isoformat()},
    ).status_code == 422

    # unknown product, variant of another product, duplicate lines
    assert api.post(f"{API}/plans", headers=admin,
                    json={"name": "P", "products": [{"product_id": 9999}]}).status_code == 400
    assert api.post(f"{API}/plans", headers=admin,
                    json={"name": "P", "products": [{"product_id": p1["id"], "variant_id": other_variant["id"]}]}
                    ).status_code == 400
    assert api.post(f"{API}/plans", headers=admin,
                    json={"name": "P", "products": [{"product_id": p1["id"]}, {"product_id": p1["id"]}]}
                    ).status_code == 400


def test_plan_prices_and_line_replacement(api, users):
    admin, customer = users["admin"], users["customer"]
    product = make_product(api, admin, sales_price="100.00")
    variant = api.post(
        f"{API}/products/{product['id']}/variants",
        headers=admin,
        json={"variant_name": "Pro", "additional_price": "25.50"},
    ).json()

    plan = make_plan(
        api, admin,
        products=[
            {"product_id": product["id"], "variant_id": variant["id"], "default_quantity": 2},
            {"product_id": product["id"], "unit_price": "90.00"},
        ],
    )
    prices = sorted(Decimal(line["effective_unit_price"]) for line in plan["products"])
    assert prices == [Decimal("90.00"), Decimal("125.50")]

    # replacing lines, including re-adding the same product
    res = api.put(
        f"{API}/plans/{plan['id']}",
        headers=admin,
        json={"products": [{"product_id": product["id"], "default_quantity": 5}]},
    )
    assert res.status_code == 200
    assert len(res.json()["products"]) == 1
    assert res.json()["products"][0]["default_quantity"] == 5

    # customers only see lines whose product is still active
    api.put(f"{API}/products/{product['id']}", headers=admin, json={"is_active": False})
    seen = api.get(f"{API}/plans/{plan['id']}", headers=customer).json()
    assert seen["products"] == []


def test_soft_delete_and_in_use_protection(api, users):
    admin, staff = users["admin"], users["staff"]
    product = make_product(api, admin)
    plan = make_plan(api, admin, products=[{"product_id": product["id"]}])

    # blocked while an active plan uses it
    assert api.delete(f"{API}/products/{product['id']}", headers=admin).status_code == 409

    assert api.delete(f"{API}/plans/{plan['id']}", headers=admin).status_code == 204
    assert api.delete(f"{API}/products/{product['id']}", headers=admin).status_code == 204

    assert api.get(f"{API}/products/{product['id']}", headers=staff).status_code == 404
    assert api.get(f"{API}/products", headers=staff).json()["total"] == 0
    assert api.delete(f"{API}/products/{product['id']}", headers=staff).status_code == 403