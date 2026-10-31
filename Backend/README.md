# Brightloop Subscription Management API

Subscription and recurring-billing backend built with FastAPI, SQLAlchemy and Alembic.

Core relationship: **Customer → Quotation → Subscription → Invoice → Payment**

## Setup

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` in `Backend/`:

```
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/brightloop
SECRET_KEY=change-me
CORS_ORIGINS=["http://localhost:4200"]
```

```powershell
alembic upgrade head            # create tables
python -m app.db.seed           # seed roles (ADMIN, INTERNAL, CUSTOMER)
python scripts\seed_demo.py     # optional: demo data (see below)
uvicorn app.main:app --reload   # API on http://127.0.0.1:8000, docs at /docs
```

## Tests

```powershell
pytest                # 70 tests, in-memory SQLite
alembic check         # models and migrations in sync
```

## Roles

| Role | Can do |
|---|---|
| ADMIN | Everything, including catalog and discount setup |
| INTERNAL (staff) | Quotations, subscriptions, invoices, payments, reports |
| CUSTOMER | View and confirm own quotations, read own invoices, payments and notifications |

Customers never see other customers' records (404, not 403) and never see draft invoices or internal notes.

## Demo data

`python scripts\seed_demo.py` creates accounts (password `Strong#Pass1`):

- `admin@brightloop.demo`, `staff@brightloop.demo`
- Customers: `acme@`, `globex@`, `initech@`, `umbrella@brightloop.demo`

and one invoice in each state: paid, partially paid, overdue, and a draft with a discount (`WELCOME10`).
Run it once; it does nothing if the admin user already exists.

## Modules and endpoints (all under `/api/v1`)

| Module | Key endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login` |
| Catalog | `/taxes`, `/products`, `/plans` |
| Quotations | `POST /quotations`, `/{id}/send`, `/{id}/confirm` |
| Subscriptions | `POST /subscriptions`, `/{id}/activate`, pause, renew, close |
| Invoices | `POST /invoices/generate`, `/{id}/confirm`, `/{id}/cancel`, `/{id}/apply-discount`, `/{id}/pdf`, billing run |
| Discounts | `/discounts` (percentage or fixed, limits, product mapping) |
| Payments | `POST /payments` (single or split across invoices), `/{id}/refund`, `GET /payments` |
| Reports | `GET /reports/summary`, `/reports/revenue`, `/reports/overdue` (staff only) |
| Notifications | `GET /notifications`, `/unread-count`, `POST /{id}/read`, `/read-all`, `/send-overdue-reminders` |

Full request and response schemas: open `/docs`.

## Business rules

- Billing creates **draft** invoices. Staff review, optionally apply a discount, then confirm.
- Tax, price and discount are **snapshots** copied onto invoice lines.
- One invoice per subscription billing period (unique constraint). Cancelled invoices keep their period.
- Invoices become OVERDUE lazily on read once past the due date and unpaid.
- Payments must not exceed the invoice balance (overpayment is rejected with 400).
- A payment can be split across several invoices of the same customer.
- Refunds reverse the allocations, lower `paid_amount` and recalculate invoice status.
- MRR = ACTIVE subscriptions only, line amounts before tax, normalised to one month by plan interval.
- Notifications are in-app only (receipts, invoice confirmed, overdue, refunds, reminders).

## End-to-end walkthrough (PowerShell)

```powershell
$api = "http://127.0.0.1:8000/api/v1"
function Login($email) {
  $r = Invoke-RestMethod "$api/auth/login" -Method Post -ContentType "application/json" `
       -Body (@{email=$email; password="Strong#Pass1"} | ConvertTo-Json)
  @{Authorization = "Bearer $($r.access_token)"}
}
$staff = Login "staff@brightloop.demo"
$admin = Login "admin@brightloop.demo"

# dashboard
Invoke-RestMethod "$api/reports/summary" -Headers $staff

# overdue invoices
Invoke-RestMethod "$api/reports/overdue" -Headers $staff

# record a payment against invoice 3
Invoke-RestMethod "$api/payments" -Method Post -Headers $staff -ContentType "application/json" `
  -Body (@{method="UPI"; invoice_id=3; amount="100.00"} | ConvertTo-Json)

# send reminders for overdue invoices
Invoke-RestMethod "$api/notifications/send-overdue-reminders" -Method Post -Headers $staff
```

To build the flow from scratch: register a customer, create a quotation (staff), send it, confirm it
(customer), create and activate a subscription from the quotation, generate the invoice, confirm it,
and record the payment.
