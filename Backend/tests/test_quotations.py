from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import Quotation

PASSWORD = "Strong#Pass1"
API = "/api/v1"


def _login(api, email):
    res = api.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _register(api, email):
    res = api.post(
        f"{API}/auth/register",
        json={"full_name": email.split("@")[0], "email": email, "password": PASSWORD},
    )
    assert res.status_code == 201
    headers = _login(api, email)
    return headers, api.get(f"{API}/customers/me", headers=headers).json()["id"]


@pytest.fixture()
def world(api, make_staff):
    make_staff("admin@example.com", "ADMIN")
    make_staff("staff@example.com", "INTERNAL")
    admin = _login(api, "admin@example.com")
    staff = _login(api, "staff@example.com")
    cust_a, cust_a_id = _register(api, "a@example.com")
    cust_b, cust_b_id = _register(api, "b@example.com")

    tax = api.post(f"{API}/taxes", headers=admin, json={"name": "GST", "rate": "18"}).json()
    product = api.post(
        f"{API}/products",
        headers=admin,
        json={"name": "Storage", "sales_price": "100.00", "tax_ids": [tax["id"]]},
    ).json()
    plan = api.post(
        f"{API}/plans",
        headers=admin,
        json={"name": "Monthly", "products": [{"product_id": product["id"]}]},
    ).json()
    return {
        "admin": admin, "staff": staff,
        "a": cust_a, "a_id": cust_a_id, "b": cust_b, "b_id": cust_b_id,
        "product": product, "plan": plan, "tax": tax,
    }


def quote_body(w, **over):
    body = {
        "customer_id": w["a_id"],
        "plan_id": w["plan"]["id"],
        "lines": [{"product_id": w["product"]["id"], "quantity": 2, "discount_amount": "20.00"}],
    }
    body.update(over)
    return body


def make_quote(api, w, **over):
    res = api.post(f"{API}/quotations", headers=w["staff"], json=quote_body(w, **over))
    assert res.status_code == 201, res.text
    return res.json()


def test_totals_and_numbering(api, world):
    q = make_quote(api, world)
    assert q["quotation_number"].startswith("QT-") and q["status"] == "DRAFT"
    assert Decimal(q["subtotal"]) == Decimal("200.00")
    assert Decimal(q["discount_amount"]) == Decimal("20.00")
    assert Decimal(q["tax_amount"]) == Decimal("32.40")  # (200 - 20) * 18%
    assert Decimal(q["total_amount"]) == Decimal("212.40")
    line = q["lines"][0]
    assert Decimal(line["tax_rate"]) == Decimal("18") and Decimal(line["line_total"]) == Decimal("212.40")
    assert q["customer_name"] == "a"
    assert date.fromisoformat(q["valid_until"]) == date.today() + timedelta(days=30)


def test_create_validation_and_roles(api, world):
    w = world
    url = f"{API}/quotations"
    assert api.post(url, json=quote_body(w)).status_code == 401
    assert api.post(url, headers=w["a"], json=quote_body(w)).status_code == 403

    pid = w["product"]["id"]
    assert api.post(url, headers=w["staff"], json=quote_body(w, lines=[])).status_code == 400
    assert api.post(url, headers=w["staff"], json=quote_body(w, customer_id=9999)).status_code == 404
    assert api.post(url, headers=w["staff"], json=quote_body(w, plan_id=9999)).status_code == 400
    assert api.post(url, headers=w["staff"], json=quote_body(w, lines=[{"product_id": 9999}])).status_code == 400
    assert api.post(url, headers=w["staff"], json=quote_body(w, lines=[{"product_id": pid, "discount_amount": "500"}])).status_code == 400
    assert api.post(url, headers=w["staff"], json=quote_body(w, lines=[{"product_id": pid, "quantity": 0}])).status_code == 422
    assert api.post(url, headers=w["staff"], json=quote_body(w, lines=[{"product_id": pid, "discount_amount": "-1"}])).status_code == 422
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert api.post(url, headers=w["staff"], json=quote_body(w, valid_until=yesterday)).status_code == 400


def test_price_sources_and_snapshot(api, world):
    w = world
    pid = w["product"]["id"]
    override_plan = api.post(
        f"{API}/plans",
        headers=w["admin"],
        json={"name": "Override", "products": [{"product_id": pid, "unit_price": "90.00"}]},
    ).json()

    from_plan = make_quote(
        api, w, plan_id=override_plan["id"], lines=[{"product_id": pid, "quantity": 1}]
    )
    assert Decimal(from_plan["lines"][0]["unit_price"]) == Decimal("90.00")

    explicit = make_quote(api, w, lines=[{"product_id": pid, "unit_price": "75.00"}])
    assert Decimal(explicit["lines"][0]["unit_price"]) == Decimal("75.00")

    quote = make_quote(api, w)
    api.put(f"{API}/products/{pid}", headers=w["admin"], json={"sales_price": "500.00"})
    api.delete(f"{API}/taxes/{w['tax']['id']}", headers=w["admin"])
    again = api.get(f"{API}/quotations/{quote['id']}", headers=w["staff"]).json()
    assert Decimal(again["total_amount"]) == Decimal("212.40")


def test_templates(api, world):
    w = world
    pid = w["product"]["id"]
    body = {
        "name": "Starter",
        "plan_id": w["plan"]["id"],
        "validity_days": 10,
        "lines": [{"product_id": pid, "quantity": 3}],
    }
    assert api.post(f"{API}/quotation-templates", headers=w["staff"], json=body).status_code == 403
    assert api.get(f"{API}/quotation-templates", headers=w["a"]).status_code == 403
    created = api.post(f"{API}/quotation-templates", headers=w["admin"], json=body)
    assert created.status_code == 201
    template = created.json()
    assert api.get(f"{API}/quotation-templates", headers=w["staff"]).json()["total"] == 1
    assert api.post(
        f"{API}/quotation-templates", headers=w["admin"],
        json={"name": "Bad", "lines": [{"product_id": 9999}]},
    ).status_code == 400

    res = api.post(
        f"{API}/quotations",
        headers=w["staff"],
        json={"customer_id": w["a_id"], "template_id": template["id"]},
    )
    assert res.status_code == 201, res.text
    q = res.json()
    assert q["plan_id"] == w["plan"]["id"] and q["template_id"] == template["id"]
    assert q["lines"][0]["quantity"] == 3
    assert date.fromisoformat(q["valid_until"]) == date.today() + timedelta(days=10)

    assert api.delete(f"{API}/quotation-templates/{template['id']}", headers=w["admin"]).status_code == 204
    again = api.post(
        f"{API}/quotations",
        headers=w["staff"],
        json={"customer_id": w["a_id"], "template_id": template["id"]},
    )
    assert again.status_code == 400


def test_ownership_and_lifecycle(api, world):
    w = world
    q = make_quote(api, w)
    url = f"{API}/quotations/{q['id']}"

    # drafts are invisible to customers
    assert api.get(url, headers=w["a"]).status_code == 404
    assert api.get(f"{API}/quotations", headers=w["a"]).json()["total"] == 0
    assert api.post(f"{url}/confirm", headers=w["staff"]).status_code == 400  # not sent yet

    assert api.post(f"{url}/send", headers=w["a"]).status_code == 403
    sent = api.post(f"{url}/send", headers=w["staff"])
    assert sent.status_code == 200 and sent.json()["status"] == "SENT"
    assert api.post(f"{url}/send", headers=w["staff"]).status_code == 400

    # owner sees it (notes hidden), other customer cannot probe it
    owned = api.get(url, headers=w["a"])
    assert owned.status_code == 200 and owned.json()["notes"] is None
    assert api.get(url, headers=w["b"]).status_code == 404
    assert api.post(f"{url}/confirm", headers=w["b"]).status_code == 404
    assert api.post(f"{url}/reject", headers=w["b"]).status_code == 404
    assert api.get(f"{API}/quotations", headers=w["b"]).json()["total"] == 0
    assert api.get(f"{API}/quotations", headers=w["a"]).json()["total"] == 1

    # sent quotes are locked
    assert api.put(url, headers=w["staff"], json={"notes": "x"}).status_code == 400
    assert api.delete(url, headers=w["staff"]).status_code == 400

    done = api.post(f"{url}/confirm", headers=w["a"])
    assert done.status_code == 200 and done.json()["status"] == "CONFIRMED"
    assert api.post(f"{url}/confirm", headers=w["a"]).status_code == 400
    assert api.post(f"{url}/reject", headers=w["a"]).status_code == 400

    # rejection path
    q2 = make_quote(api, w)
    api.post(f"{API}/quotations/{q2['id']}/send", headers=w["staff"])
    rejected = api.post(f"{API}/quotations/{q2['id']}/reject", headers=w["a"])
    assert rejected.json()["status"] == "REJECTED"

    # staff filters
    only_sent = api.get(f"{API}/quotations?status=CONFIRMED", headers=w["staff"]).json()
    assert only_sent["total"] == 1
    by_customer = api.get(f"{API}/quotations?customer_id={w['b_id']}", headers=w["staff"]).json()
    assert by_customer["total"] == 0


def test_expiry(api, world, session_factory):
    w = world
    q = make_quote(api, w)
    url = f"{API}/quotations/{q['id']}"
    api.post(f"{url}/send", headers=w["staff"])

    with session_factory() as db:
        row = db.get(Quotation, q["id"])
        row.valid_until = date.today() - timedelta(days=1)
        db.commit()

    assert api.get(url, headers=w["a"]).json()["status"] == "EXPIRED"
    assert api.post(f"{url}/confirm", headers=w["a"]).status_code == 400

    # a draft past its validity cannot be sent until the date is extended
    d = make_quote(api, w)
    with session_factory() as db:
        row = db.get(Quotation, d["id"])
        row.valid_until = date.today() - timedelta(days=1)
        db.commit()
    assert api.post(f"{API}/quotations/{d['id']}/send", headers=w["staff"]).status_code == 400
    extended = (date.today() + timedelta(days=5)).isoformat()
    assert api.put(f"{API}/quotations/{d['id']}", headers=w["staff"], json={"valid_until": extended}).status_code == 200
    assert api.post(f"{API}/quotations/{d['id']}/send", headers=w["staff"]).status_code == 200


def test_edit_and_delete_draft(api, world):
    w = world
    pid = w["product"]["id"]
    q = make_quote(api, w)
    url = f"{API}/quotations/{q['id']}"

    res = api.put(
        url,
        headers=w["staff"],
        json={"notes": "internal", "lines": [{"product_id": pid, "quantity": 1}]},
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["lines"]) == 1 and Decimal(body["total_amount"]) == Decimal("118.00")
    assert body["notes"] == "internal"
    assert api.put(url, headers=w["staff"], json={"lines": []}).status_code == 400

    assert api.delete(url, headers=w["staff"]).status_code == 204
    assert api.get(url, headers=w["staff"]).status_code == 404
    assert api.get(f"{API}/quotations", headers=w["staff"]).json()["total"] == 0