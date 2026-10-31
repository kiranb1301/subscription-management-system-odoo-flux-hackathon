from datetime import date, timedelta

try:
    from tests.test_payments import _set_invoice, confirmed_invoice, invoice_of, pay, world  # noqa: F401
except ImportError:  # tests folder is not a package
    from test_payments import _set_invoice, confirmed_invoice, invoice_of, pay, world  # noqa: F401

API = "/api/v1"


def notes(api, headers, query=""):
    res = api.get(f"{API}/notifications{query}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def unread(api, headers):
    return api.get(f"{API}/notifications/unread-count", headers=headers).json()["unread"]


def test_invoice_confirmed_notifies_owner_only(api, world):
    w = world
    inv = confirmed_invoice(api, w, "a")
    mine = notes(api, w["a"])
    assert mine["total"] == 1
    n = mine["items"][0]
    assert n["title"] == "Invoice confirmed" and n["status"] == "SENT"
    assert n["related_type"] == "invoice" and n["related_id"] == inv["id"]
    assert inv["invoice_number"] in n["message"]
    assert notes(api, w["b"])["total"] == 0
    assert unread(api, w["a"]) == 1
    assert api.get(f"{API}/notifications").status_code == 401


def test_payment_and_refund_notifications(api, world):
    w = world
    inv = confirmed_invoice(api, w, "a")
    p = pay(api, w, invoice_id=inv["id"], amount="100").json()
    assert "Payment received" in [n["title"] for n in notes(api, w["a"])["items"]]

    assert api.post(f"{API}/payments/{p['id']}/refund", headers=w["staff"]).status_code == 200
    titles = [n["title"] for n in notes(api, w["a"])["items"]]
    assert "Payment refunded" in titles
    assert notes(api, w["b"])["total"] == 0


def test_mark_read_and_read_all(api, world):
    w = world
    inv = confirmed_invoice(api, w, "a")
    confirmed_invoice(api, w, "b")
    pay(api, w, invoice_id=inv["id"], amount="100")
    assert unread(api, w["a"]) == 2 and unread(api, w["b"]) == 1

    first = notes(api, w["a"])["items"][0]
    assert api.post(f"{API}/notifications/{first['id']}/read", headers=w["b"]).status_code == 404
    done = api.post(f"{API}/notifications/{first['id']}/read", headers=w["a"])
    assert done.status_code == 200 and done.json()["status"] == "READ" and done.json()["read_at"]
    assert unread(api, w["a"]) == 1 and notes(api, w["a"], "?unread_only=true")["total"] == 1

    assert api.post(f"{API}/notifications/read-all", headers=w["a"]).json() == {"updated": 1}
    assert unread(api, w["a"]) == 0 and unread(api, w["b"]) == 1
    assert api.post(f"{API}/notifications/999999/read", headers=w["a"]).status_code == 404


def test_overdue_notice_and_reminders(api, world, session_factory):
    w = world
    inv = confirmed_invoice(api, w, "b")
    _set_invoice(session_factory, inv["id"], due_date=date.today() - timedelta(days=2))
    assert invoice_of(api, w, inv)["status"] == "OVERDUE"
    assert "Invoice overdue" in [n["title"] for n in notes(api, w["b"])["items"]]

    url = f"{API}/notifications/send-overdue-reminders"
    assert api.post(url, headers=w["b"]).status_code == 403
    assert api.post(url, headers=w["staff"]).json() == {"created": 1}
    assert api.post(url, headers=w["staff"]).json() == {"created": 0}  # once per day
    assert "Payment reminder" in [n["title"] for n in notes(api, w["b"])["items"]]
    assert "Payment reminder" not in [n["title"] for n in notes(api, w["a"])["items"]]