from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import Subscription
from app.models.enums import BillingInterval
from app.services.dates import advance_date

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


def _plan(api, admin, name, **over):
    body = {"name": name, "billing_interval": "MONTHLY", "interval_count": 1, **over}
    res = api.post(f"{API}/plans", headers=admin, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _set_sub(session_factory, sub_id, **fields):
    with session_factory() as db:
        row = db.get(Subscription, sub_id)
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
    today = date.today()
    plan = _plan(
        api, admin, "Main",
        allow_pause=True, allow_renewal=True,
        end_date=(today + timedelta(days=60)).isoformat(),
    )
    return {
        "admin": admin, "staff": staff, "a": a, "a_id": a_id, "b": b, "b_id": b_id,
        "product": product, "plan": plan,
    }


def confirmed_quote(api, w, plan, who="a"):
    body = {
        "customer_id": w[f"{who}_id"],
        "plan_id": plan["id"],
        "lines": [{"product_id": w["product"]["id"], "quantity": 2, "discount_amount": "20.00"}],
    }
    res = api.post(f"{API}/quotations", headers=w["staff"], json=body)
    assert res.status_code == 201, res.text
    q = res.json()
    assert api.post(f"{API}/quotations/{q['id']}/send", headers=w["staff"]).status_code == 200
    assert api.post(f"{API}/quotations/{q['id']}/confirm", headers=w[who]).status_code == 200
    return q


def make_sub(api, w, plan=None, who="a", **over):
    q = confirmed_quote(api, w, plan or w["plan"], who)
    res = api.post(
        f"{API}/subscriptions", headers=w["staff"], json={"quotation_id": q["id"], **over}
    )
    assert res.status_code == 201, res.text
    return res.json()


def active_sub(api, w, plan=None, who="a"):
    sub = make_sub(api, w, plan, who)
    res = api.post(f"{API}/subscriptions/{sub['id']}/activate", headers=w["staff"])
    assert res.status_code == 200, res.text
    return res.json()


def test_advance_date():
    monthly = BillingInterval.MONTHLY
    assert advance_date(date(2026, 1, 31), monthly, 1) == date(2026, 2, 28)
    assert advance_date(date(2026, 11, 30), monthly, 3) == date(2027, 2, 28)
    assert advance_date(date(2024, 2, 29), BillingInterval.YEARLY, 1) == date(2025, 2, 28)
    assert advance_date(date(2026, 1, 1), BillingInterval.WEEKLY, 2) == date(2026, 1, 15)
    assert advance_date(date(2026, 1, 1), BillingInterval.DAILY, 10) == date(2026, 1, 11)


def test_create_from_confirmed_quotation(api, world):
    w = world
    url = f"{API}/subscriptions"
    body = {
        "customer_id": w["a_id"],
        "plan_id": w["plan"]["id"],
        "lines": [{"product_id": w["product"]["id"], "quantity": 2, "discount_amount": "20.00"}],
    }
    q = api.post(f"{API}/quotations", headers=w["staff"], json=body).json()

    assert api.post(url, json={"quotation_id": q["id"]}).status_code == 401
    assert api.post(url, headers=w["a"], json={"quotation_id": q["id"]}).status_code == 403
    assert api.post(url, headers=w["staff"], json={"quotation_id": 0}).status_code == 422
    assert api.post(url, headers=w["staff"], json={"quotation_id": 9999}).status_code == 404
    assert api.post(url, headers=w["staff"], json={"quotation_id": q["id"]}).status_code == 400  # draft
    api.post(f"{API}/quotations/{q['id']}/send", headers=w["staff"])
    assert api.post(url, headers=w["staff"], json={"quotation_id": q["id"]}).status_code == 400  # sent
    api.post(f"{API}/quotations/{q['id']}/confirm", headers=w["a"])

    res = api.post(url, headers=w["staff"], json={"quotation_id": q["id"], "payment_terms_days": 15})
    assert res.status_code == 201, res.text
    sub = res.json()
    assert sub["status"] == "CONFIRMED" and sub["subscription_number"].startswith("SUB-")
    assert sub["customer_id"] == w["a_id"] and sub["quotation_id"] == q["id"]
    assert sub["payment_terms_days"] == 15 and sub["pending_request"] is None
    assert len(sub["lines"]) == 1
    line = sub["lines"][0]
    assert line["quantity"] == 2 and Decimal(line["tax_rate"]) == Decimal("18")
    assert Decimal(line["line_total"]) == Decimal("212.40")
    assert sorted(sub["available_actions"]) == ["activate", "cancel"]

    # one live subscription per quotation, but a cancelled one can be replaced
    assert api.post(url, headers=w["staff"], json={"quotation_id": q["id"]}).status_code == 409
    assert api.post(f"{url}/{sub['id']}/cancel", headers=w["staff"]).status_code == 200
    assert api.post(url, headers=w["staff"], json={"quotation_id": q["id"]}).status_code == 201


def test_activation(api, world):
    w = world
    today = date.today()
    sub = make_sub(api, w)
    url = f"{API}/subscriptions/{sub['id']}"

    assert api.post(f"{url}/activate", headers=w["a"]).status_code == 403
    res = api.post(f"{url}/activate", headers=w["staff"])
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ACTIVE"
    assert body["start_date"] == today.isoformat()
    assert body["next_billing_date"] == today.isoformat()
    assert body["expiry_date"] == w["plan"]["end_date"]
    assert api.post(f"{url}/activate", headers=w["staff"]).status_code == 400

    # start date rules
    s2 = make_sub(api, w)
    u2 = f"{API}/subscriptions/{s2['id']}/activate"
    yesterday = (today - timedelta(days=1)).isoformat()
    assert api.post(u2, headers=w["staff"], json={"start_date": yesterday}).status_code == 400
    future = today + timedelta(days=5)
    res = api.post(u2, headers=w["staff"], json={"start_date": future.isoformat()})
    assert res.status_code == 200
    assert res.json()["start_date"] == future.isoformat()
    assert res.json()["next_billing_date"] == future.isoformat()

    # a plan that has already ended cannot be activated
    ended = _plan(api, w["admin"], "Ended", end_date=yesterday)
    s3 = make_sub(api, w, plan=ended)
    assert api.post(f"{API}/subscriptions/{s3['id']}/activate", headers=w["staff"]).status_code == 400


def test_pause_and_resume(api, world, session_factory):
    w = world
    today = date.today()
    sub = active_sub(api, w)
    url = f"{API}/subscriptions/{sub['id']}"

    assert api.post(f"{url}/pause", headers=w["b"]).status_code == 404  # not the owner
    assert api.post(f"{url}/resume", headers=w["a"]).status_code == 400  # not paused
    paused = api.post(f"{url}/pause", headers=w["a"])
    assert paused.status_code == 200 and paused.json()["status"] == "PAUSED"
    assert "resume" in paused.json()["available_actions"]
    assert api.post(f"{url}/pause", headers=w["a"]).status_code == 400

    _set_sub(session_factory, sub["id"], next_billing_date=today - timedelta(days=3))
    resumed = api.post(f"{url}/resume", headers=w["staff"])
    assert resumed.status_code == 200 and resumed.json()["status"] == "ACTIVE"
    assert resumed.json()["next_billing_date"] == today.isoformat()

    # plans that do not allow pausing
    nopause = _plan(api, w["admin"], "NoPause", allow_pause=False)
    s2 = active_sub(api, w, plan=nopause)
    u2 = f"{API}/subscriptions/{s2['id']}"
    assert "pause" not in api.get(u2, headers=w["a"]).json()["available_actions"]
    assert api.post(f"{u2}/pause", headers=w["a"]).status_code == 400
    assert api.post(f"{u2}/pause", headers=w["staff"]).status_code == 400


def test_close_and_cancel(api, world):
    w = world
    sub = active_sub(api, w)
    url = f"{API}/subscriptions/{sub['id']}"

    assert "close" not in api.get(url, headers=w["staff"]).json()["available_actions"]
    assert api.post(f"{url}/close", headers=w["staff"]).status_code == 400
    assert api.post(f"{url}/close", headers=w["a"]).status_code == 403
    assert api.post(f"{url}/cancel", headers=w["a"]).status_code == 403

    res = api.post(f"{url}/cancel", headers=w["staff"], json={"reason": "Fraud check"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "CANCELLED" and body["next_billing_date"] is None
    assert body["available_actions"] == []
    assert api.post(f"{url}/cancel", headers=w["staff"]).status_code == 400
    history = api.get(f"{url}/history", headers=w["staff"]).json()
    assert "Fraud check" in history[-1]["reason"]

    # plans that allow early close
    early = _plan(api, w["admin"], "Early", allow_early_close=True)
    s2 = active_sub(api, w, plan=early)
    closed = api.post(f"{API}/subscriptions/{s2['id']}/close", headers=w["staff"])
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED" and closed.json()["next_billing_date"] is None

    # a confirmed (not yet active) subscription can be cancelled
    s3 = make_sub(api, w)
    assert api.post(f"{API}/subscriptions/{s3['id']}/cancel", headers=w["staff"]).status_code == 200


def test_renewal_and_expiry(api, world, session_factory):
    w = world
    today = date.today()
    plan_end = date.fromisoformat(w["plan"]["end_date"])
    sub = active_sub(api, w)
    url = f"{API}/subscriptions/{sub['id']}"

    assert api.post(f"{url}/renew", headers=w["a"], json={"periods": 1}).status_code == 403
    assert api.post(f"{url}/renew", headers=w["staff"], json={"periods": 0}).status_code == 422
    res = api.post(f"{url}/renew", headers=w["staff"], json={"periods": 2})
    assert res.status_code == 200
    assert res.json()["status"] == "ACTIVE"
    assert res.json()["expiry_date"] == advance_date(plan_end, BillingInterval.MONTHLY, 2).isoformat()

    # plan rules
    norenew = _plan(
        api, w["admin"], "NoRenew", allow_renewal=False,
        end_date=(today + timedelta(days=30)).isoformat(),
    )
    s2 = active_sub(api, w, plan=norenew)
    assert api.post(f"{API}/subscriptions/{s2['id']}/renew", headers=w["staff"]).status_code == 400
    openended = _plan(api, w["admin"], "OpenEnded", allow_renewal=True)
    s3 = active_sub(api, w, plan=openended)
    assert api.post(f"{API}/subscriptions/{s3['id']}/renew", headers=w["staff"]).status_code == 400

    # lazy expiry, then renewal reactivates
    _set_sub(session_factory, sub["id"], expiry_date=today - timedelta(days=1))
    body = api.get(url, headers=w["a"]).json()
    assert body["status"] == "EXPIRED" and body["next_billing_date"] is None
    assert "request_renew" in body["available_actions"]
    assert api.post(f"{url}/pause", headers=w["a"]).status_code == 400
    back = api.post(f"{url}/renew", headers=w["staff"], json={"periods": 1})
    assert back.status_code == 200
    assert back.json()["status"] == "ACTIVE"
    assert back.json()["expiry_date"] == advance_date(today, BillingInterval.MONTHLY, 1).isoformat()
    assert back.json()["next_billing_date"] == today.isoformat()

    # auto_close plans close instead of expiring
    auto = _plan(
        api, w["admin"], "Auto", auto_close=True, allow_renewal=True,
        end_date=(today + timedelta(days=30)).isoformat(),
    )
    s4 = active_sub(api, w, plan=auto)
    _set_sub(session_factory, s4["id"], expiry_date=today - timedelta(days=1))
    assert api.get(f"{API}/subscriptions/{s4['id']}", headers=w["a"]).json()["status"] == "CLOSED"


def test_customer_requests(api, world):
    w = world
    sub = active_sub(api, w)
    other = active_sub(api, w)
    url = f"{API}/subscriptions/{sub['id']}"

    assert api.post(f"{url}/request-cancel", headers=w["staff"]).status_code == 403
    assert api.post(f"{url}/request-cancel", headers=w["b"]).status_code == 404

    res = api.post(f"{url}/request-cancel", headers=w["a"], json={"reason": "Too expensive"})
    assert res.status_code == 200
    assert res.json()["pending_request"] == "CANCEL"
    assert "request_cancel" not in res.json()["available_actions"]
    assert api.post(f"{url}/request-cancel", headers=w["a"]).status_code == 409

    pending = api.get(f"{API}/subscriptions?has_request=true", headers=w["staff"]).json()
    assert pending["total"] == 1 and pending["items"][0]["id"] == sub["id"]
    assert "dismiss_request" in pending["items"][0]["available_actions"]
    assert api.get(f"{API}/subscriptions?has_request=false", headers=w["staff"]).json()["total"] == 1

    # staff declines the request; a decline needs a pending request
    assert api.post(f"{API}/subscriptions/{other['id']}/dismiss-request", headers=w["staff"]).status_code == 400
    assert api.post(f"{url}/dismiss-request", headers=w["a"]).status_code == 403
    declined = api.post(f"{url}/dismiss-request", headers=w["staff"], json={"reason": "Contract lock-in"})
    assert declined.status_code == 200 and declined.json()["pending_request"] is None

    # renewal request, cleared when staff renews
    asked = api.post(f"{url}/request-renew", headers=w["a"])
    assert asked.status_code == 200 and asked.json()["pending_request"] == "RENEW"
    assert api.post(f"{url}/request-renew", headers=w["a"]).status_code == 409
    renewed = api.post(f"{url}/renew", headers=w["staff"], json={"periods": 1})
    assert renewed.status_code == 200 and renewed.json()["pending_request"] is None

    # plans without renewal reject the request
    norenew = _plan(
        api, w["admin"], "NoRenew", allow_renewal=False,
        end_date=(date.today() + timedelta(days=30)).isoformat(),
    )
    s3 = active_sub(api, w, plan=norenew)
    assert api.post(f"{API}/subscriptions/{s3['id']}/request-renew", headers=w["a"]).status_code == 400


def test_ownership_listing_and_history(api, world):
    w = world
    s1 = active_sub(api, w, who="a")
    s2 = make_sub(api, w, who="b")
    url = f"{API}/subscriptions/{s1['id']}"

    assert api.get(f"{API}/subscriptions", headers=w["a"]).json()["total"] == 1
    assert api.get(f"{API}/subscriptions", headers=w["b"]).json()["total"] == 1
    assert api.get(f"{API}/subscriptions", headers=w["staff"]).json()["total"] == 2
    assert api.get(url, headers=w["a"]).status_code == 200
    assert api.get(url, headers=w["b"]).status_code == 404
    assert api.get(f"{url}/history", headers=w["b"]).status_code == 404
    assert api.get(f"{API}/subscriptions/999999", headers=w["a"]).status_code == 404
    assert api.get(f"{API}/subscriptions").status_code == 401

    by_status = api.get(f"{API}/subscriptions?status=ACTIVE", headers=w["staff"]).json()
    assert by_status["total"] == 1 and by_status["items"][0]["id"] == s1["id"]
    by_customer = api.get(f"{API}/subscriptions?customer_id={w['b_id']}", headers=w["staff"]).json()
    assert by_customer["total"] == 1 and by_customer["items"][0]["id"] == s2["id"]
    by_number = api.get(
        f"{API}/subscriptions?search={s1['subscription_number']}", headers=w["staff"]
    ).json()
    assert by_number["total"] == 1
    page = api.get(f"{API}/subscriptions?page=1&page_size=1", headers=w["staff"]).json()
    assert len(page["items"]) == 1 and page["total"] == 2

    api.post(f"{url}/pause", headers=w["a"])
    staff_history = api.get(f"{url}/history", headers=w["staff"]).json()
    assert [h["to_status"] for h in staff_history] == ["CONFIRMED", "ACTIVE", "PAUSED"]
    assert staff_history[0]["from_status"] is None
    assert staff_history[-1]["changed_by"] is not None
    customer_history = api.get(f"{url}/history", headers=w["a"]).json()
    assert len(customer_history) == 3
    assert all(h["changed_by"] is None for h in customer_history)