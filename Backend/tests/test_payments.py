from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import Invoice

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


def _set_invoice(session_factory, invoice_id, **fields):
    with session_factory() as db:
        row = db.get(Invoice, invoice_id)
        for key, value in fields.items():
            setattr(row, key, value)
        db.commit()


@pytest.fixture()
def world(api, make_staff):
    make_staff("admin@example.com", "ADMIN")
    make_staff("staff@example.com", "INTERNAL")
    admin = _login(api, "admin@example.com")
    staff = _login(api, "staff@example.com")
    a, a_id = _register(api, "a@example.com")
    b, b_id = _register(api, "b@example.com")

    tax = api.post(f"{API}/taxes", headers=admin, json={"name": "GST", "rate": "18"}).json()
    product = api.post(
        f"{API}/products",
        headers=admin,
        json={"name": "Storage", "sales_price": "100.00", "tax_ids": [tax["id"]]},
    ).json()
    res = api.post(
        f"{API}/plans",
        headers=admin,
        json={
            "name": "Main", "billing_interval": "MONTHLY", "interval_count": 1,
            "allow_pause": True, "allow_renewal": True,
            "end_date": (date.today() + timedelta(days=60)).isoformat(),
        },
    )
    assert res.status_code == 201, res.text
    return {
        "admin": admin, "staff": staff, "a": a, "a_id": a_id, "b": b, "b_id": b_id,
        "product": product, "plan": res.json(),
    }


def active_sub(api, w, who="a"):
    body = {
        "customer_id": w[f"{who}_id"],
        "plan_id": w["plan"]["id"],
        "lines": [{"product_id": w["product"]["id"], "quantity": 2, "discount_amount": "20.00"}],
    }
    q = api.post(f"{API}/quotations", headers=w["staff"], json=body)
    assert q.status_code == 201, q.text
    q = q.json()
    assert api.post(f"{API}/quotations/{q['id']}/send", headers=w["staff"]).status_code == 200
    assert api.post(f"{API}/quotations/{q['id']}/confirm", headers=w[who]).status_code == 200
    sub = api.post(f"{API}/subscriptions", headers=w["staff"], json={"quotation_id": q["id"]})
    assert sub.status_code == 201, sub.text
    act = api.post(f"{API}/subscriptions/{sub.json()['id']}/activate", headers=w["staff"])
    assert act.status_code == 200, act.text
    return act.json()


def draft_invoice(api, w, who="a"):
    sub = active_sub(api, w, who)
    res = api.post(
        f"{API}/invoices/generate", headers=w["staff"], json={"subscription_id": sub["id"]}
    )
    assert res.status_code == 201, res.text
    return res.json()


def confirmed_invoice(api, w, who="a"):
    inv = draft_invoice(api, w, who)
    res = api.post(f"{API}/invoices/{inv['id']}/confirm", headers=w["staff"])
    assert res.status_code == 200, res.text
    return res.json()


def pay(api, w, **body):
    body.setdefault("method", "CASH")
    return api.post(f"{API}/payments", headers=w["staff"], json=body)


def invoice_of(api, w, inv):
    return api.get(f"{API}/invoices/{inv['id']}", headers=w["staff"]).json()


def test_full_payment_marks_invoice_paid(api, world):
    w = world
    inv = confirmed_invoice(api, w)
    assert Decimal(inv["total_amount"]) == Decimal("212.40")

    res = pay(api, w, invoice_id=inv["id"], amount="212.40")
    assert res.status_code == 201, res.text
    p = res.json()
    assert p["status"] == "COMPLETED" and p["payment_reference"].startswith("PAY-")
    assert p["customer_id"] == w["a_id"] and p["available_actions"] == ["refund"]
    assert len(p["allocations"]) == 1
    assert p["allocations"][0]["invoice_number"] == inv["invoice_number"]

    after = invoice_of(api, w, inv)
    assert after["status"] == "PAID"
    assert Decimal(after["paid_amount"]) == Decimal("212.40")
    assert Decimal(after["balance_due"]) == 0
    history = api.get(f"{API}/invoices/{inv['id']}/history", headers=w["staff"]).json()
    assert history[-1]["to_status"] == "PAID"
    assert api.get(f"{API}/invoices/{inv['id']}", headers=w["a"]).json()["status"] == "PAID"


def test_partial_payments_then_paid(api, world):
    w = world
    inv = confirmed_invoice(api, w)

    assert pay(api, w, invoice_id=inv["id"], amount="100").status_code == 201
    mid = invoice_of(api, w, inv)
    assert mid["status"] == "PARTIALLY_PAID"
    assert Decimal(mid["paid_amount"]) == Decimal("100")
    assert Decimal(mid["balance_due"]) == Decimal("112.40")
    assert api.post(f"{API}/invoices/{inv['id']}/cancel", headers=w["staff"]).status_code == 400

    assert pay(api, w, invoice_id=inv["id"], amount="112.41").status_code == 400  # overpayment
    assert pay(api, w, invoice_id=inv["id"], amount="112.40").status_code == 201
    assert invoice_of(api, w, inv)["status"] == "PAID"
    assert pay(api, w, invoice_id=inv["id"], amount="1").status_code == 400  # already paid


def test_payment_validation_and_permissions(api, world):
    w = world
    draft = draft_invoice(api, w)
    inv = confirmed_invoice(api, w)
    other = confirmed_invoice(api, w, "b")

    assert pay(api, w, invoice_id=draft["id"], amount="10").status_code == 400  # not confirmed
    assert pay(api, w, invoice_id=inv["id"], amount="0").status_code == 422
    assert pay(api, w, invoice_id=inv["id"], amount="-5").status_code == 422
    assert pay(api, w, invoice_id=inv["id"], amount="10.123").status_code == 422
    assert pay(api, w, amount="10").status_code == 422  # no target
    both = pay(
        api, w, invoice_id=inv["id"], amount="10",
        allocations=[{"invoice_id": inv["id"], "amount": "10"}],
    )
    assert both.status_code == 422
    assert pay(api, w, invoice_id=999999, amount="10").status_code == 404

    short = pay(api, w, amount="100", allocations=[{"invoice_id": inv["id"], "amount": "50"}])
    assert short.status_code == 400  # allocations do not add up
    twice = pay(
        api, w, amount="100",
        allocations=[{"invoice_id": inv["id"], "amount": "50"}, {"invoice_id": inv["id"], "amount": "50"}],
    )
    assert twice.status_code == 400  # same invoice twice
    wrong = pay(api, w, customer_id=w["b_id"], invoice_id=inv["id"], amount="10")
    assert wrong.status_code == 400  # invoice belongs to another customer

    body = {"method": "CASH", "invoice_id": inv["id"], "amount": "10"}
    assert api.post(f"{API}/payments", headers=w["a"], json=body).status_code == 403
    assert api.post(f"{API}/payments", json=body).status_code == 401

    assert Decimal(invoice_of(api, w, inv)["paid_amount"]) == 0
    assert Decimal(invoice_of(api, w, other)["paid_amount"]) == 0
    assert api.get(f"{API}/payments", headers=w["staff"]).json()["total"] == 0


def test_one_payment_across_invoices(api, world):
    w = world
    ia1 = confirmed_invoice(api, w, "a")
    ia2 = confirmed_invoice(api, w, "a")
    ib = confirmed_invoice(api, w, "b")

    mixed = pay(
        api, w, amount="100",
        allocations=[{"invoice_id": ia2["id"], "amount": "50"}, {"invoice_id": ib["id"], "amount": "50"}],
    )
    assert mixed.status_code == 400  # two customers in one payment
    assert Decimal(invoice_of(api, w, ib)["paid_amount"]) == 0

    res = pay(
        api, w, customer_id=w["a_id"], amount="300",
        allocations=[
            {"invoice_id": ia1["id"], "amount": "212.40"},
            {"invoice_id": ia2["id"], "amount": "87.60"},
        ],
    )
    assert res.status_code == 201, res.text
    assert len(res.json()["allocations"]) == 2
    assert invoice_of(api, w, ia1)["status"] == "PAID"
    second = invoice_of(api, w, ia2)
    assert second["status"] == "PARTIALLY_PAID"
    assert Decimal(second["balance_due"]) == Decimal("124.80")


def test_payment_reference_must_be_unique(api, world):
    w = world
    inv = confirmed_invoice(api, w)
    first = pay(api, w, invoice_id=inv["id"], amount="10", payment_reference="REF-1")
    assert first.status_code == 201 and first.json()["payment_reference"] == "REF-1"
    assert pay(api, w, invoice_id=inv["id"], amount="10", payment_reference="REF-1").status_code == 409
    assert Decimal(invoice_of(api, w, inv)["paid_amount"]) == Decimal("10")


def test_overdue_invoice_payments(api, world, session_factory):
    w = world
    inv = confirmed_invoice(api, w)
    _set_invoice(session_factory, inv["id"], due_date=date.today() - timedelta(days=1))
    assert invoice_of(api, w, inv)["status"] == "OVERDUE"

    assert pay(api, w, invoice_id=inv["id"], amount="50").status_code == 201
    part = invoice_of(api, w, inv)
    assert part["status"] == "OVERDUE" and Decimal(part["paid_amount"]) == Decimal("50")

    assert pay(api, w, invoice_id=inv["id"], amount="162.40").status_code == 201
    assert invoice_of(api, w, inv)["status"] == "PAID"


def test_refund_restores_invoice(api, world):
    w = world
    inv = confirmed_invoice(api, w)
    p = pay(api, w, invoice_id=inv["id"], amount="212.40", note="first").json()
    url = f"{API}/payments/{p['id']}/refund"

    assert api.post(url, headers=w["a"]).status_code == 403
    assert api.post(f"{API}/payments/999999/refund", headers=w["staff"]).status_code == 404

    res = api.post(url, headers=w["staff"], json={"reason": "Customer request"})
    assert res.status_code == 200, res.text
    refunded = res.json()
    assert refunded["status"] == "REFUNDED" and refunded["available_actions"] == []
    assert "Customer request" in refunded["note"]

    after = invoice_of(api, w, inv)
    assert after["status"] == "CONFIRMED" and Decimal(after["paid_amount"]) == 0
    history = api.get(f"{API}/invoices/{inv['id']}/history", headers=w["staff"]).json()
    assert "refunded" in history[-1]["reason"]

    assert api.post(url, headers=w["staff"]).status_code == 400  # already refunded
    assert pay(api, w, invoice_id=inv["id"], amount="212.40").status_code == 201
    assert invoice_of(api, w, inv)["status"] == "PAID"


def test_refund_on_overdue_invoice(api, world, session_factory):
    w = world
    inv = confirmed_invoice(api, w, "b")
    _set_invoice(session_factory, inv["id"], due_date=date.today() - timedelta(days=1))
    p = pay(api, w, invoice_id=inv["id"], amount="50").json()

    res = api.post(f"{API}/payments/{p['id']}/refund", headers=w["staff"])
    assert res.status_code == 200 and res.json()["status"] == "REFUNDED"
    after = invoice_of(api, w, inv)
    assert after["status"] == "OVERDUE" and Decimal(after["paid_amount"]) == 0


def test_payment_access_and_filters(api, world):
    w = world
    staff = w["staff"]
    ia = confirmed_invoice(api, w, "a")
    ib = confirmed_invoice(api, w, "b")
    pa = pay(api, w, invoice_id=ia["id"], amount="100", method="UPI", note="internal memo").json()
    pb = pay(api, w, invoice_id=ib["id"], amount="50", method="CARD", payment_reference="B-REF").json()

    def count(path, headers=staff):
        return api.get(f"{API}/payments{path}", headers=headers).json()["total"]

    assert count("") == 2
    assert count(f"?customer_id={w['b_id']}") == 1
    assert count(f"?invoice_id={ia['id']}") == 1
    assert count("?method=CARD") == 1
    assert count("?status=COMPLETED") == 2 and count("?status=REFUNDED") == 0
    assert count("?search=B-REF") == 1
    page = api.get(f"{API}/payments?page=1&page_size=1", headers=staff).json()
    assert len(page["items"]) == 1 and page["total"] == 2

    assert count("", w["a"]) == 1 and count("", w["b"]) == 1
    assert count(f"?invoice_id={ib['id']}", w["a"]) == 0  # cannot probe other customers

    own = api.get(f"{API}/payments/{pa['id']}", headers=w["a"])
    assert own.status_code == 200 and own.json()["note"] is None
    assert own.json()["available_actions"] == []
    assert api.get(f"{API}/payments/{pa['id']}", headers=staff).json()["note"] == "internal memo"
    assert api.get(f"{API}/payments/{pa['id']}", headers=w["b"]).status_code == 404
    assert api.get(f"{API}/payments/{pb['id']}", headers=w["a"]).status_code == 404
    assert api.get(f"{API}/payments/999999", headers=staff).status_code == 404
    assert api.get(f"{API}/payments").status_code == 401