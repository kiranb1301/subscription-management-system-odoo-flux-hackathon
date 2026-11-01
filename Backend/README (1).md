# Brightloop Subscription Management System

A subscription and recurring-billing platform: product catalogue, plans, quotations, subscriptions, automated invoicing, discounts, payments and refunds, role-based access, notifications, revenue reporting and a customer self-service view.

| Part | Stack | Status |
|---|---|---|
| `Backend/` | FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, JWT, APScheduler, ReportLab | Complete, 79 pytest tests and 401 Postman cases pass |
| `Frontend/` | Angular 22 (standalone, Vitest) | Project scaffold only; no screens built yet |

---

## 1. Repository layout

```
.
├── Backend/
│   ├── app/
│   │   ├── main.py, core/        app factory, exceptions, security, permissions
│   │   ├── api/deps.py           auth + role dependencies, pagination
│   │   ├── api/v1/routes/        auth, users, customers, taxes, products, plans,
│   │   │                         quotation_templates, quotations, subscriptions,
│   │   │                         discounts, invoices, billing, payments,
│   │   │                         reports, notifications, health
│   │   ├── models/ schemas/      SQLAlchemy models, Pydantic schemas
│   │   ├── services/             all business rules (routes stay thin)
│   │   ├── tasks/scheduler.py    daily billing / overdue / expiry job
│   │   ├── db/                   session, base, role seed
│   │   └── settings/config.py    environment-driven settings
│   ├── migrations/ alembic.ini   Alembic (written for MySQL)
│   ├── scripts/seed_demo.py      demo data
│   ├── tests/                    pytest suite (79 tests)
│   └── requirements.txt
└── Frontend/                     Angular workspace
```

## 2. Core flow

```
Customer -> Quotation -> Subscription -> Invoice -> Payment -> Reports
```

| Object | Statuses |
|---|---|
| Quotation | DRAFT, SENT, CONFIRMED, REJECTED, EXPIRED |
| Subscription | CONFIRMED, ACTIVE, PAUSED, CLOSED, CANCELLED, EXPIRED |
| Invoice | DRAFT, CONFIRMED, PARTIALLY_PAID, PAID, OVERDUE, CANCELLED |
| Payment | COMPLETED, REFUNDED |

### Business rules worth knowing

- **Roles:** `ADMIN`, `INTERNAL` (staff), `CUSTOMER`. A customer account is created only through `POST /auth/register`; staff are added by an admin through `POST /users`.
- **Passwords:** more than 8 characters with upper case, lower case and a special character; stored with Argon2.
- **Billing:** the billing run creates **DRAFT** invoices for ACTIVE, due subscriptions. There is one invoice per subscription billing period, so running it again creates nothing new. Missed periods are caught up (up to 12 per run).
- **Overdue** status is applied lazily whenever invoices or payments are read, and by the daily scheduler job.
- **Payments** can pay one invoice (`invoice_id`) or be split (`allocations`). Overpayment is rejected, references are unique, and a refund reverses its allocations and reopens the invoice.
- **Discounts** are applied **manually by code** on a draft invoice (`apply-discount`) and can be removed again, which releases the use.
- **Customers** see only their own non-draft invoices and their own subscriptions, payments and notifications. Someone else's record returns **404**, not 403. Internal notes and cost prices are hidden from customers.
- **MRR** counts ACTIVE subscriptions normalised to a month; ARR = 12 x MRR.
- **E-mails** (verification, reset, invoices) are printed to the console when `SMTP_HOST` is empty.

## 3. Backend setup

Requirements: Python 3.11+ (tested on 3.13). MySQL 8 for production; SQLite works for local development.

```bash
cd Backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # then edit
```

### 3.1 Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./brightloop.db` | e.g. `mysql+pymysql://user:pass@localhost:3306/brightloop_db` |
| `SECRET_KEY` | `change-me-in-env` | JWT signing key. **Change it.** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 30 | Access token lifetime |
| `CORS_ORIGINS` | `["http://localhost:4200"]` | Allowed browser origins (JSON list) |
| `FRONTEND_URL` | `http://localhost:4200` | Used in e-mail links |
| `PASSWORD_RESET_EXPIRE_MINUTES` / `EMAIL_VERIFY_EXPIRE_HOURS` | 30 / 24 | Token lifetimes |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS` | empty / 587 | Leave `SMTP_HOST` empty for console e-mails |
| `SCHEDULER_ENABLED` | `false` | Turn on the daily background job |
| `SCHEDULER_HOUR`, `SCHEDULER_MINUTE`, `SCHEDULER_TIMEZONE` | 2, 0, Asia/Kolkata | When the job runs |
| `REDIS_URL` | `redis://localhost:6379/0` | Reserved for caching/queues |

### 3.2 Database

**MySQL (intended path):**

```bash
# create the database first, put its URL in .env, then:
alembic upgrade head
python -m app.db.seed          # roles ADMIN / INTERNAL / CUSTOMER
python scripts/seed_demo.py    # demo users, catalogue, subscriptions, invoices
```

**SQLite (quick local run):** the migrations use MySQL-only constraint changes and fail on SQLite, so create the tables from the models instead:

```bash
export DATABASE_URL=sqlite:///./brightloop.db
python -c "import app.models; from app.db.base import Base; from app.db.session import engine; Base.metadata.create_all(engine)"
python -m app.db.seed
python scripts/seed_demo.py
```

### 3.3 Run

```bash
uvicorn app.main:app --reload --port 8000
```

- Interactive docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

### 3.4 Demo accounts (after `seed_demo.py`)

All use the password `Strong#Pass1`.

| Role | E-mail |
|---|---|
| Admin | `admin@brightloop.demo` |
| Staff | `staff@brightloop.demo` |
| Customer | `acme@brightloop.demo` (and others listed by the seed script) |

## 4. API reference (prefix `/api/v1`)

Authenticate with `POST /auth/login` (JSON body `{"email", "password"}`) and send `Authorization: Bearer <token>`.

| Area | Endpoints | Access |
|---|---|---|
| Auth | `POST /auth/register`, `/auth/login`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/verify-email`, `/auth/resend-verification`; `GET /auth/me` | public / any user |
| Users | `GET, POST /users`; `PATCH /users/{id}/active` | admin |
| Customers | `GET, PUT /customers/me`; `GET /customers`; `GET, PUT /customers/{id}` | customer (own) / staff |
| Taxes | `GET, POST /taxes`; `GET, PUT, DELETE /taxes/{id}` | read: any, write: admin |
| Products | `GET, POST /products`; `GET, PUT, DELETE /products/{id}`; `POST /products/{id}/variants`; `PUT, DELETE /products/{id}/variants/{vid}` | read: any, write: admin |
| Plans | `GET, POST /plans`; `GET, PUT, DELETE /plans/{id}` | read: any, write: admin |
| Quotation templates | `GET, POST /quotation-templates`; `GET, PUT, DELETE /quotation-templates/{id}` | staff |
| Quotations | `GET, POST /quotations`; `GET, PUT, DELETE /quotations/{id}`; `POST .../send`, `/confirm`, `/reject` | staff |
| Subscriptions | `GET, POST /subscriptions`; `GET /{id}`, `/{id}/history`; `POST /{id}/activate`, `/pause`, `/resume`, `/close`, `/cancel`, `/renew`, `/dismiss-request`; customer: `POST /{id}/request-cancel`, `/request-renew` | staff / customer (own) |
| Discounts | `GET, POST /discounts`; `GET, PUT, DELETE /discounts/{id}` | admin |
| Invoices | `GET /invoices`; `POST /invoices/generate`; `GET, PUT /{id}`; `GET /{id}/history`, `/{id}/pdf`; `POST /{id}/apply-discount`, `/remove-discount`, `/confirm`, `/cancel` | staff; customers read own non-draft + PDF |
| Billing | `POST /billing/run`; `GET /billing/jobs` | staff |
| Payments | `GET, POST /payments`; `GET /payments/{id}`; `POST /payments/{id}/refund` | staff write; customers read own |
| Reports | `GET /reports/summary`, `/reports/revenue?group_by=day\|month&from&to`, `/reports/overdue` | staff |
| Notifications | `GET /notifications`, `/unread-count`; `POST /read-all`, `/{id}/read`, `/send-overdue-reminders` (staff) | any user (own) |

List endpoints are paginated (`page`, `page_size`) and return `{items, total, page, page_size}`. Errors use `{"detail": ...}`.

## 5. Testing

### 5.1 Unit and integration tests (pytest)

```bash
cd Backend
pytest -q          # 79 tests, in-memory SQLite
```

### 5.2 Postman / newman (401 cases)

Files: `Brightloop.postman_collection.json`, `Brightloop.postman_environment.json`, and `Brightloop_API_Test_Cases.pdf` (case-by-case document with results).

1. Start the backend on port 8000 with the demo seed loaded (section 3).
2. Import both JSON files into Postman and run the collection in order (Collection Runner), or:

```bash
npm i -g newman
newman run Brightloop.postman_collection.json -e Brightloop.postman_environment.json
```

The suite creates its own customers, staff and catalogue per run, so it can be repeated. Cases are order-dependent (later ones reuse ids saved by earlier ones). Every request checks its status code and a response time under 2 seconds.

Modules: health, authentication, user management, customers, taxes, products and variants, plans, quotation templates, quotations, subscriptions, discounts, billing and invoices, payments, notifications, reports, security matrix, e-mail token flows.

**E-mail token flows (folder 16):** the verification and reset tokens appear in the server console. Copy them into the environment variables `verify_token` and `reset_token` and run that folder; without them its 4 cases are skipped.

Latest recorded result: 401 of 401 cases passed (1,154 assertions, 0 failed), average response 12 ms.

## 6. Scheduler

With `SCHEDULER_ENABLED=true` a daily job (default 02:00 Asia/Kolkata) runs the billing job (draft invoices for due subscriptions) and then sends in-app overdue reminders to customers. The same billing logic can be triggered by staff at any time through `POST /billing/run`.

## 7. Frontend (Angular)

The `Frontend/` folder is an untouched Angular CLI project (Angular 22, `@angular/build`, Vitest, Prettier). No screens or API wiring exist yet.

```bash
cd Frontend
npm install
npm start          # http://localhost:4200
npm run build
npm test
```

The backend already allows the `http://localhost:4200` origin. Suggested structure for the build-out:

```
src/app/
  core/       auth service, JWT interceptor, route guards (role based), API models
  shared/     tables, forms, status badges
  features/   auth, dashboard, customers, catalogue, plans, quotations,
              subscriptions, invoices, payments, notifications, portal
```

Screens map to the API: login/register/reset, staff dashboard (`/reports/*`), catalogue and plans, quotation to subscription workflow, invoice and payment management, and a customer portal (own subscriptions, invoices, PDF download, cancel/renew requests, notifications).

## 8. Known limitations

- The frontend is a scaffold.
- Alembic migrations target MySQL and were not run in this review (no MySQL instance); SQLite was used for all verification.
- Discounts are not applied automatically at billing time; staff apply them by code on draft invoices.
- Response time was measured with demo-sized data only; the under-2-second target has not been load-tested with thousands of subscriptions.
- Overdue invoices cannot be created directly through the API (they arise when a due date passes).
- Billing creates DRAFT invoices, which staff then confirm.
