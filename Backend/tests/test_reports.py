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
        f"{API}/products", headers=admin,
        json={"name": "Storage", "sales_price": "100.00", "tax_ids": [tax["id"]]},
    ).json()
    res = api.post(
        f"{API}/plans", headers=admin,
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


def active_sub(api, w, who="a", plan=None):
    plan = plan or w["plan"]
    body = {
        "customer_id": w[f"{who}_id"], "plan_id": plan["id"],
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


def confirmed_invoice(api, w, who="a"):
    sub = active_sub(api, w, who)
    inv = api.post(f"{API}/invoices/generate", headers=w["staff"], json={"subscription_id": sub["id"]})
    assert inv.status_code == 201, inv.text
    res = api.post(f"{API}/invoices/{inv.json()['id']}/confirm", headers=w["staff"])
    assert res.status_code == 200, res.text
    return res.json()


def pay(api, w, inv, amount):
    res = api.post(
        f"{API}/payments", headers=w["staff"],
        json={"method": "CASH", "invoice_id": inv["id"], "amount": amount},
    )
    assert res.status_code == 201, res.text
    return res.json()


def report(api, w, path, who="staff"):
    res = api.get(f"{API}/reports{path}", headers=w[who])
    assert res.status_code == 200, res.text
    return res.json()


def test_summary_dashboard_numbers(api, world, session_factory):
    w = world
    ia = confirmed_invoice(api, w, "a")
    ib = confirmed_invoice(api, w, "b")
    pay(api, w, ia, "100")
    _set_invoice(session_factory, ib["id"], due_date=date.today() - timedelta(days=1))

    s = report(api, w, "/summary")
    assert Decimal(s["mrr"]) == Decimal("360.00") and Decimal(s["arr"]) == Decimal("4320.00")
    assert s["active_subscriptions"] == 2 and s["subscriptions_by_status"]["ACTIVE"] == 2
    assert Decimal(s["revenue_collected"]) == Decimal("100.00")
    assert Decimal(s["refunded_total"]) == 0
    assert Decimal(s["outstanding_amount"]) == Decimal("324.80") and s["outstanding_count"] == 2
    assert Decimal(s["overdue_amount"]) == Decimal("212.40") and s["overdue_count"] == 1
    assert s["invoices_by_status"]["PARTIALLY_PAID"] == 1
    assert s["invoices_by_status"]["OVERDUE"] == 1 and s["invoices_by_status"]["PAID"] == 0


def test_mrr_normalises_billing_interval(api, world):
    w = world
    res = api.post(
        f"{API}/plans", headers=w["admin"],
        json={"name": "Yearly", "billing_interval": "YEARLY", "interval_count": 1},
    )
    assert res.status_code == 201, res.text
    active_sub(api, w, "a", plan=res.json())
    s = report(api, w, "/summary")
    assert Decimal(s["mrr"]) == Decimal("15.00") and Decimal(s["arr"]) == Decimal("180.00")
    assert s["active_subscriptions"] == 1


def test_revenue_report_and_refunds(api, world):
    w = world
    pa = pay(api, w, confirmed_invoice(api, w, "a"), "100")
    pb = pay(api, w, confirmed_invoice(api, w, "b"), "50")

    r = report(api, w, "/revenue")
    assert r["group_by"] == "month" and Decimal(r["total_collected"]) == Decimal("150.00")
    assert len(r["points"]) == 1 and r["points"][0]["payments"] == 2
    assert r["points"][0]["period"] == date.today().strftime("%Y-%m")
    day = report(api, w, "/revenue?group_by=day")
    assert day["points"][0]["period"] == date.today().isoformat()

    assert api.post(f"{API}/payments/{pb['id']}/refund", headers=w["staff"]).status_code == 200
    r = report(api, w, "/revenue")
    assert Decimal(r["total_collected"]) == Decimal("100.00")
    assert Decimal(r["total_refunded"]) == Decimal("50.00")
    s = report(api, w, "/summary")
    assert Decimal(s["revenue_collected"]) == Decimal("100.00")
    assert Decimal(s["refunded_total"]) == Decimal("50.00")

    old = report(api, w, "/revenue?from=2000-01-01&to=2000-01-31")
    assert Decimal(old["total_collected"]) == 0 and old["points"] == []
    assert api.get(f"{API}/reports/revenue?from=2025-02-01&to=2025-01-01", headers=w["staff"]).status_code == 400
    assert api.get(f"{API}/reports/revenue?group_by=year", headers=w["staff"]).status_code == 422


def test_overdue_report(api, world, session_factory):
    w = world
    confirmed_invoice(api, w, "a")
    ib = confirmed_invoice(api, w, "b")
    assert report(api, w, "/overdue")["total"] == 0

    _set_invoice(session_factory, ib["id"], due_date=date.today() - timedelta(days=3))
    pay(api, w, ib, "12.40")
    page = report(api, w, "/overdue")
    assert page["total"] == 1
    row = page["items"][0]
    assert row["invoice_id"] == ib["id"] and row["customer_id"] == w["b_id"]
    assert row["days_overdue"] == 3 and Decimal(row["balance_due"]) == Decimal("200.00")
    assert row["customer_name"]


def test_reports_are_staff_only(api, world):
    w = world
    for path in ("/summary", "/revenue", "/overdue"):
        assert api.get(f"{API}/reports{path}", headers=w["a"]).status_code == 403
        assert api.get(f"{API}/reports{path}").status_code == 401
        assert api.get(f"{API}/reports{path}", headers=w["admin"]).status_code == 200