import os, sys
from datetime import date, timedelta

sys.path.insert(0, os.getcwd())

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.db.seed import seed_roles
from app.db.session import get_db
from app.main import app
from app.models import Invoice, Role, User

PASSWORD = "Strong#Pass1"
API = "/api/v1"
api = TestClient(app)
db = next(get_db())
seed_roles(db)


def make_staff(email, role):
    row = db.query(Role).filter_by(name=role).one()
    db.add(User(full_name=f"{role.title()} User", email=email,
                password_hash=hash_password(PASSWORD), role_id=row.id, is_email_verified=True))
    db.commit()


def login(email):
    res = api.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def ok(res, code):
    assert res.status_code == code, f"{res.request.url}: {res.status_code} {res.text}"
    return res.json()


if db.query(User).filter_by(email="admin@brightloop.demo").first():
    print("Demo data already exists. Nothing to do.")
    sys.exit(0)

make_staff("admin@brightloop.demo", "ADMIN")
make_staff("staff@brightloop.demo", "INTERNAL")
admin, staff = login("admin@brightloop.demo"), login("staff@brightloop.demo")

customers = {}
for key, name in [("acme", "Acme Corp"), ("globex", "Globex Ltd"), ("initech", "Initech"), ("umbrella", "Umbrella Co")]:
    email = f"{key}@brightloop.demo"
    ok(api.post(f"{API}/auth/register", json={"full_name": name, "email": email, "password": PASSWORD}), 201)
    headers = login(email)
    customers[key] = (headers, ok(api.get(f"{API}/customers/me", headers=headers), 200)["id"])

tax = ok(api.post(f"{API}/taxes", headers=admin, json={"name": "GST", "rate": "18"}), 201)
storage = ok(api.post(f"{API}/products", headers=admin,
                      json={"name": "Cloud Storage", "sales_price": "100.00", "tax_ids": [tax["id"]]}), 201)
support = ok(api.post(f"{API}/products", headers=admin,
                      json={"name": "Premium Support", "sales_price": "250.00", "tax_ids": [tax["id"]]}), 201)
monthly = ok(api.post(f"{API}/plans", headers=admin,
                      json={"name": "Monthly", "billing_interval": "MONTHLY", "interval_count": 1,
                            "allow_pause": True, "allow_renewal": True}), 201)
yearly = ok(api.post(f"{API}/plans", headers=admin,
                     json={"name": "Yearly", "billing_interval": "YEARLY", "interval_count": 1,
                           "allow_renewal": True}), 201)
ok(api.post(f"{API}/discounts", headers=admin,
            json={"code": "WELCOME10", "name": "Welcome 10%", "discount_type": "PERCENTAGE",
                  "discount_value": "10"}), 201)


def onboard(key, plan, product, qty):
    headers, cid = customers[key]
    body = {"customer_id": cid, "plan_id": plan["id"],
            "lines": [{"product_id": product["id"], "quantity": qty, "discount_amount": "0.00"}]}
    q = ok(api.post(f"{API}/quotations", headers=staff, json=body), 201)
    ok(api.post(f"{API}/quotations/{q['id']}/send", headers=staff), 200)
    ok(api.post(f"{API}/quotations/{q['id']}/confirm", headers=headers), 200)
    sub = ok(api.post(f"{API}/subscriptions", headers=staff, json={"quotation_id": q["id"]}), 201)
    ok(api.post(f"{API}/subscriptions/{sub['id']}/activate", headers=staff), 200)
    inv = ok(api.post(f"{API}/invoices/generate", headers=staff, json={"subscription_id": sub["id"]}), 201)
    return inv


def confirm(inv):
    return ok(api.post(f"{API}/invoices/{inv['id']}/confirm", headers=staff), 200)


def pay(inv, amount, method="UPI"):
    ok(api.post(f"{API}/payments", headers=staff,
                json={"method": method, "invoice_id": inv["id"], "amount": str(amount)}), 201)


paid = confirm(onboard("acme", monthly, storage, 5))
pay(paid, paid["total_amount"])

partial = confirm(onboard("globex", monthly, support, 2))
pay(partial, "300.00", "BANK_TRANSFER")

late = confirm(onboard("initech", yearly, storage, 10))
row = db.get(Invoice, late["id"])
row.due_date = date.today() - timedelta(days=12)
db.commit()

draft = onboard("umbrella", monthly, storage, 3)
ok(api.post(f"{API}/invoices/{draft['id']}/apply-discount", headers=staff, json={"code": "WELCOME10"}), 200)

print("Demo data created.")
print("  admin@brightloop.demo / staff@brightloop.demo / acme@brightloop.demo ... all use", PASSWORD)
print("  Invoices: 1 paid, 1 partially paid, 1 overdue, 1 draft with discount")
