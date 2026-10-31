from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import Invoice, Subscription
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
    plan = _plan(
        api, admin, "Main",
        allow_pause=True, allow_renewal=True,
        end_date=(date.today() + timedelta(days=60)).isoformat(),
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


def active_sub(api, w, plan=None, who="a", **over):
    sub = make_sub(api, w, plan, who, **over)
    res = api.post(f"{API}/subscriptions/{sub['id']}/activate", headers=w["staff"])
    assert res.status_code == 200, res.text
    return res.json()


def gen(api, w, sub):
    res = api.post(
        f"{API}/invoices/generate", headers=w["staff"], json={"subscription_id": sub["id"]}
    )
    assert res.status_code == 201, res.text
    return res.json()


def make_discount(api, w, **over):
    body = {
        "code": "save10", "name": "Save 10", "discount_type": "PERCENTAGE",
        "discount_value": "10", **over,
    }
    res = api.post(f"{API}/discounts", headers=w["admin"], json=body)
    assert res.status_code == 201, res.text
    return res.json()


def apply(api, w, inv, code):
    return api.post(
        f"{API}/invoices/{inv['id']}/apply-discount", headers=w["staff"], json={"code": code}
    )


def test_discount_admin_rules(api, world):
    w = world
    url = f"{API}/discounts"
    body = {"code": "WELCOME", "name": "Welcome", "discount_type": "PERCENTAGE", "discount_value": "10"}

    assert api.get(url).status_code == 401
    assert api.get(url, headers=w["a"]).status_code == 403
    assert api.get(url, headers=w["staff"]).status_code == 200
    assert api.post(url, headers=w["staff"], json=body).status_code == 403
    assert api.post(url, headers=w["a"], json=body).status_code == 403

    admin = w["admin"]
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    bad_bodies = [
        {**body, "discount_value": "150"},
        {**body, "discount_value": "0"},
        {**body, "discount_value": "-5"},
        {**body, "code": "a b"},
        {**body, "code": "xy"},
        {**body, "start_date": date.today().isoformat(), "end_date": yesterday},
        {**body, "min_purchase_amount": "-1"},
        {**body, "usage_limit": 0},
        {**body, "min_quantity": 0},
    ]
    for bad in bad_bodies:
        assert api.post(url, headers=admin, json=bad).status_code == 422, bad
    assert api.post(url, headers=admin, json={**body, "product_ids": [9999]}).status_code == 400

    created = api.post(url, headers=admin, json={**body, "code": "welcome"})
    assert created.status_code == 201
    discount = created.json()
    assert discount["code"] == "WELCOME" and discount["used_count"] == 0
    assert discount["product_ids"] == []
    assert api.post(url, headers=admin, json={**body, "code": "Welcome"}).status_code == 409

    # updates: merged validation, product list replacement
    d_url = f"{url}/{discount['id']}"
    ok = api.put(d_url, headers=admin, json={"discount_value": "15", "name": "Welcome 15"})
    assert ok.status_code == 200 and Decimal(ok.json()["discount_value"]) == Decimal("15")
    assert api.put(d_url, headers=admin, json={"discount_value": "150"}).status_code == 400
    assert api.put(d_url, headers=w["staff"], json={"name": "x"}).status_code == 403
    pid = w["product"]["id"]
    mapped = api.put(d_url, headers=admin, json={"product_ids": [pid]})
    assert mapped.status_code == 200 and mapped.json()["product_ids"] == [pid]
    cleared = api.put(d_url, headers=admin, json={"product_ids": []})
    assert cleared.json()["product_ids"] == []
    assert api.put(d_url, headers=admin, json={"product_ids": [9999]}).status_code == 400
    assert api.get(f"{url}/999999", headers=w["staff"]).status_code == 404

    # deactivate and filter
    assert api.delete(d_url, headers=admin).status_code == 204
    assert api.get(d_url, headers=w["staff"]).json()["is_active"] is False
    assert api.get(f"{url}?is_active=false", headers=w["staff"]).json()["total"] == 1
    assert api.get(f"{url}?search=WELC", headers=w["staff"]).json()["total"] == 1
    assert api.get(f"{url}?is_active=true", headers=w["staff"]).json()["total"] == 0


def test_generate_invoice_and_totals(api, world):
    w = world
    today = date.today()
    sub = active_sub(api, w, payment_terms_days=15)
    inv = gen(api, w, sub)

    assert inv["invoice_number"].startswith("INV-") and inv["status"] == "DRAFT"
    assert inv["customer_id"] == w["a_id"] and inv["customer_name"] == "a"
    assert inv["subscription_number"] == sub["subscription_number"]
    assert inv["invoice_date"] == today.isoformat()
    assert inv["due_date"] == (today + timedelta(days=15)).isoformat()
    assert inv["billing_period_start"] == today.isoformat()
    expected_end = advance_date(today, BillingInterval.MONTHLY, 1) - timedelta(days=1)
    assert inv["billing_period_end"] == expected_end.isoformat()
    assert Decimal(inv["subtotal"]) == Decimal("200.00")
    assert Decimal(inv["discount_amount"]) == Decimal("20.00")
    assert Decimal(inv["tax_amount"]) == Decimal("32.40")
    assert Decimal(inv["total_amount"]) == Decimal("212.40")
    assert Decimal(inv["paid_amount"]) == 0 and Decimal(inv["balance_due"]) == Decimal("212.40")
    assert inv["discount_code"] is None and inv["notes"] is None
    line = inv["lines"][0]
    assert line["quantity"] == 2 and Decimal(line["tax_rate"]) == Decimal("18")
    assert line["tax_name"] == "Tax 18.00%" and Decimal(line["line_total"]) == Decimal("212.40")

    after = api.get(f"{API}/subscriptions/{sub['id']}", headers=w["staff"]).json()
    assert after["next_billing_date"] == advance_date(today, BillingInterval.MONTHLY, 1).isoformat()
    # nothing due again until the next period
    assert api.post(
        f"{API}/invoices/generate", headers=w["staff"], json={"subscription_id": sub["id"]}
    ).status_code == 400


def test_permissions_and_guards(api, world):
    w = world
    sub = active_sub(api, w)
    g = f"{API}/invoices/generate"
    body = {"subscription_id": sub["id"]}

    assert api.post(g, json=body).status_code == 401
    assert api.post(g, headers=w["a"], json=body).status_code == 403
    assert api.post(g, headers=w["staff"], json={"subscription_id": 9999}).status_code == 404
    assert api.post(g, headers=w["staff"], json={"subscription_id": 0}).status_code == 422
    not_active = make_sub(api, w)
    assert api.post(g, headers=w["staff"], json={"subscription_id": not_active["id"]}).status_code == 400

    assert api.post(f"{API}/billing/run", headers=w["a"], json={}).status_code == 403
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert api.post(f"{API}/billing/run", headers=w["staff"], json={"run_date": tomorrow}).status_code == 400
    assert api.get(f"{API}/billing/jobs", headers=w["a"]).status_code == 403
    assert api.get(f"{API}/invoices").status_code == 401


def test_billing_run_catch_up_and_idempotency(api, world, session_factory):
    w = world
    today = date.today()
    s1 = active_sub(api, w, who="a")
    s2 = active_sub(api, w, who="b")
    paused = active_sub(api, w, who="a")
    assert api.post(f"{API}/subscriptions/{paused['id']}/pause", headers=w["a"]).status_code == 200
    _set_sub(session_factory, s1["id"], next_billing_date=advance_date(today, BillingInterval.MONTHLY, -2))

    res = api.post(f"{API}/billing/run", headers=w["staff"], json={})
    assert res.status_code == 200, res.text
    job = res.json()
    assert job["status"] == "COMPLETED" and job["error_message"] is None
    assert job["subscriptions_processed"] == 2 and job["invoices_created"] == 4
    assert job["started_at"] is not None and job["finished_at"] is not None

    first = api.get(f"{API}/invoices?subscription_id={s1['id']}", headers=w["staff"]).json()
    assert first["total"] == 3
    assert {i["status"] for i in first["items"]} == {"DRAFT"}
    assert len({i["billing_period_start"] for i in first["items"]}) == 3
    assert api.get(f"{API}/invoices?subscription_id={s2['id']}", headers=w["staff"]).json()["total"] == 1
    assert api.get(f"{API}/invoices?subscription_id={paused['id']}", headers=w["staff"]).json()["total"] == 0

    # running again creates nothing
    again = api.post(f"{API}/billing/run", headers=w["staff"], json={}).json()
    assert again["invoices_created"] == 0 and again["subscriptions_processed"] == 0
    assert api.get(f"{API}/invoices", headers=w["staff"]).json()["total"] == 4

    jobs = api.get(f"{API}/billing/jobs", headers=w["staff"]).json()
    assert jobs["total"] == 2 and jobs["items"][0]["id"] > jobs["items"][1]["id"]


def test_apply_remove_and_cancel_discount(api, world):
    w = world
    staff = w["staff"]
    inv = gen(api, w, active_sub(api, w))
    url = f"{API}/invoices/{inv['id']}"
    pct = make_discount(api, w)
    d_url = f"{API}/discounts/{pct['id']}"

    assert api.post(f"{url}/apply-discount", headers=w["a"], json={"code": "SAVE10"}).status_code == 403
    res = apply(api, w, inv, "save10")  # lowercase input is normalised
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["discount_code"] == "SAVE10"
    assert Decimal(body["discount_amount"]) == Decimal("38.00")
    assert Decimal(body["tax_amount"]) == Decimal("29.16")
    assert Decimal(body["total_amount"]) == Decimal("191.16")
    assert Decimal(body["lines"][0]["discount_amount"]) == Decimal("38.00")
    assert "remove_discount" in body["available_actions"]
    assert api.get(d_url, headers=staff).json()["used_count"] == 1
    assert apply(api, w, inv, "SAVE10").status_code == 409  # one discount per invoice

    removed = api.post(f"{url}/remove-discount", headers=staff)
    assert removed.status_code == 200
    assert Decimal(removed.json()["total_amount"]) == Decimal("212.40")
    assert removed.json()["discount_code"] is None
    assert api.get(d_url, headers=staff).json()["used_count"] == 0
    assert api.post(f"{url}/remove-discount", headers=staff).status_code == 400

    # fixed amount
    make_discount(api, w, code="FLAT50", discount_type="FIXED", discount_value="50")
    flat = apply(api, w, inv, "FLAT50").json()
    assert Decimal(flat["discount_amount"]) == Decimal("70.00")
    assert Decimal(flat["tax_amount"]) == Decimal("23.40")
    assert Decimal(flat["total_amount"]) == Decimal("153.40")

    # cancelling gives the use back
    flat_id = next(
        d["id"] for d in api.get(f"{API}/discounts", headers=staff).json()["items"] if d["code"] == "FLAT50"
    )
    cancelled = api.post(f"{url}/cancel", headers=staff, json={"reason": "Wrong customer"})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert api.get(f"{API}/discounts/{flat_id}", headers=staff).json()["used_count"] == 0

    # a fixed discount is capped, a zero total is marked paid on confirmation
    inv2 = gen(api, w, active_sub(api, w))
    make_discount(api, w, code="BIGFIXED", discount_type="FIXED", discount_value="500")
    capped = apply(api, w, inv2, "BIGFIXED").json()
    assert Decimal(capped["discount_amount"]) == Decimal("200.00")
    assert Decimal(capped["total_amount"]) == Decimal("0.00")
    done = api.post(f"{API}/invoices/{inv2['id']}/confirm", headers=staff)
    assert done.status_code == 200 and done.json()["status"] == "PAID"

    # only drafts can take discounts
    inv3 = gen(api, w, active_sub(api, w))
    api.post(f"{API}/invoices/{inv3['id']}/confirm", headers=staff)
    assert apply(api, w, inv3, "SAVE10").status_code == 400
    assert api.post(f"{API}/invoices/{inv3['id']}/remove-discount", headers=staff).status_code == 400


def test_discount_rules(api, world):
    w = world
    pid = w["product"]["id"]
    inv = gen(api, w, active_sub(api, w))
    today = date.today()
    other = api.post(
        f"{API}/products", headers=w["admin"], json={"name": "Other", "sales_price": "10.00"}
    ).json()

    assert apply(api, w, inv, "NOPE").status_code == 400

    make_discount(api, w, code="OLDONE")
    old_id = api.get(f"{API}/discounts?search=OLDONE", headers=w["staff"]).json()["items"][0]["id"]
    assert api.delete(f"{API}/discounts/{old_id}", headers=w["admin"]).status_code == 204
    make_discount(api, w, code="FUTURE", start_date=(today + timedelta(days=1)).isoformat())
    make_discount(api, w, code="PAST", end_date=(today - timedelta(days=1)).isoformat())
    make_discount(api, w, code="BIGMIN", min_purchase_amount="1000")
    make_discount(api, w, code="BIGQTY", min_quantity=5)
    make_discount(api, w, code="OTHERP", product_ids=[other["id"]])
    for code in ("OLDONE", "FUTURE", "PAST", "BIGMIN", "BIGQTY", "OTHERP"):
        assert apply(api, w, inv, code).status_code == 400, code

    untouched = api.get(f"{API}/invoices/{inv['id']}", headers=w["staff"]).json()
    assert Decimal(untouched["total_amount"]) == Decimal("212.40")

    make_discount(api, w, code="MAPPED", product_ids=[pid], min_quantity=2, min_purchase_amount="100")
    ok = apply(api, w, inv, "MAPPED")
    assert ok.status_code == 200 and Decimal(ok.json()["discount_amount"]) == Decimal("38.00")


def test_discount_limits(api, world):
    w = world
    staff = w["staff"]
    ia1 = gen(api, w, active_sub(api, w, who="a"))
    ia2 = gen(api, w, active_sub(api, w, who="a"))
    ib1 = gen(api, w, active_sub(api, w, who="b"))
    ib2 = gen(api, w, active_sub(api, w, who="b"))

    make_discount(api, w, code="ONLYONE", usage_limit=1)
    assert apply(api, w, ia1, "ONLYONE").status_code == 200
    assert apply(api, w, ib1, "ONLYONE").status_code == 400  # limit reached
    api.post(f"{API}/invoices/{ia1['id']}/remove-discount", headers=staff)  # frees the slot
    assert apply(api, w, ib1, "ONLYONE").status_code == 200

    make_discount(api, w, code="PERCUST", per_customer_limit=1)
    assert apply(api, w, ia1, "PERCUST").status_code == 200
    assert apply(api, w, ia2, "PERCUST").status_code == 400  # same customer again
    assert apply(api, w, ib1, "PERCUST").status_code == 409  # ib1 already has a discount
    assert apply(api, w, ib2, "PERCUST").status_code == 200  # other customer's first use


def test_invoice_lifecycle_and_ownership(api, world, session_factory):
    w = world
    staff = w["staff"]
    today = date.today()
    inv = gen(api, w, active_sub(api, w))
    url = f"{API}/invoices/{inv['id']}"

    # drafts are invisible to customers
    assert api.get(url, headers=w["a"]).status_code == 404
    assert api.get(f"{API}/invoices", headers=w["a"]).json()["total"] == 0
    assert api.put(url, headers=w["a"], json={"notes": "x"}).status_code == 403
    assert api.post(f"{url}/confirm", headers=w["a"]).status_code == 403

    yesterday = (today - timedelta(days=1)).isoformat()
    assert api.put(url, headers=staff, json={"due_date": yesterday}).status_code == 400
    ten = (today + timedelta(days=10)).isoformat()
    edited = api.put(url, headers=staff, json={"notes": "internal", "due_date": ten})
    assert edited.status_code == 200
    assert edited.json()["due_date"] == ten and edited.json()["notes"] == "internal"

    confirmed = api.post(f"{url}/confirm", headers=staff)
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "CONFIRMED"
    assert confirmed.json()["available_actions"] == ["cancel", "download_pdf"]
    assert api.post(f"{url}/confirm", headers=staff).status_code == 400
    assert api.put(url, headers=staff, json={"notes": "late"}).status_code == 400

    # the owner sees it without internal notes; other customers cannot probe it
    owned = api.get(url, headers=w["a"])
    assert owned.status_code == 200 and owned.json()["notes"] is None
    assert owned.json()["available_actions"] == ["download_pdf"]
    assert api.get(url, headers=w["b"]).status_code == 404
    assert api.get(f"{url}/history", headers=w["b"]).status_code == 404
    assert api.get(f"{API}/invoices", headers=w["b"]).json()["total"] == 0
    assert api.get(f"{API}/invoices", headers=w["a"]).json()["total"] == 1
    assert api.get(f"{API}/invoices/999999", headers=w["a"]).status_code == 404

    staff_history = api.get(f"{url}/history", headers=staff).json()
    assert [h["to_status"] for h in staff_history] == ["DRAFT", "CONFIRMED"]
    assert staff_history[-1]["changed_by"] is not None
    customer_history = api.get(f"{url}/history", headers=w["a"]).json()
    assert len(customer_history) == 2 and all(h["changed_by"] is None for h in customer_history)

    # past the due date it becomes overdue when read
    _set_invoice(session_factory, inv["id"], due_date=today - timedelta(days=1))
    assert api.get(url, headers=w["a"]).json()["status"] == "OVERDUE"
    assert api.get(f"{API}/invoices?status=OVERDUE", headers=staff).json()["total"] == 1

    # invoices with payments cannot be cancelled
    _set_invoice(session_factory, inv["id"], paid_amount=Decimal("50.00"))
    assert api.post(f"{url}/cancel", headers=staff).status_code == 400
    assert api.post(f"{url}/cancel", headers=w["a"]).status_code == 403
    _set_invoice(session_factory, inv["id"], paid_amount=Decimal("0.00"))
    cancelled = api.post(f"{url}/cancel", headers=staff, json={"reason": "Duplicate"})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["available_actions"] == ["download_pdf"]
    assert api.post(f"{url}/cancel", headers=staff).status_code == 400
    last = api.get(f"{url}/history", headers=staff).json()[-1]
    assert "Duplicate" in last["reason"]


def test_invoice_filters(api, world):
    w = world
    staff = w["staff"]
    ia = gen(api, w, active_sub(api, w, who="a"))
    ib = gen(api, w, active_sub(api, w, who="b"))

    assert api.get(f"{API}/invoices", headers=staff).json()["total"] == 2
    by_customer = api.get(f"{API}/invoices?customer_id={w['b_id']}", headers=staff).json()
    assert by_customer["total"] == 1 and by_customer["items"][0]["id"] == ib["id"]
    by_sub = api.get(f"{API}/invoices?subscription_id={ia['subscription_id']}", headers=staff).json()
    assert by_sub["total"] == 1 and by_sub["items"][0]["id"] == ia["id"]
    by_number = api.get(f"{API}/invoices?search={ia['invoice_number']}", headers=staff).json()
    assert by_number["total"] == 1
    assert api.get(f"{API}/invoices?status=DRAFT", headers=staff).json()["total"] == 2
    assert api.get(f"{API}/invoices?status=CONFIRMED", headers=staff).json()["total"] == 0
    page = api.get(f"{API}/invoices?page=1&page_size=1", headers=staff).json()
    assert len(page["items"]) == 1 and page["total"] == 2

    api.post(f"{API}/invoices/{ia['id']}/confirm", headers=staff)
    assert api.get(f"{API}/invoices", headers=w["a"]).json()["total"] == 1
    assert api.get(f"{API}/invoices", headers=w["b"]).json()["total"] == 0


def test_invoice_pdf(api, world):
    w = world
    inv = gen(api, w, active_sub(api, w))
    url = f"{API}/invoices/{inv['id']}/pdf"

    assert api.get(url).status_code == 401
    assert api.get(url, headers=w["a"]).status_code == 404  # still a draft
    draft_pdf = api.get(url, headers=w["staff"])
    assert draft_pdf.status_code == 200 and draft_pdf.content.startswith(b"%PDF")

    api.post(f"{API}/invoices/{inv['id']}/confirm", headers=w["staff"])
    res = api.get(url, headers=w["a"])
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert inv["invoice_number"] in res.headers["content-disposition"]
    assert res.content.startswith(b"%PDF")
    assert api.get(url, headers=w["b"]).status_code == 404