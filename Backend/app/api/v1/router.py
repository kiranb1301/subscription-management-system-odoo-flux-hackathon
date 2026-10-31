from fastapi import APIRouter

from app.api.v1.routes import (
    auth,
    billing,
    customers,
    discounts,
    health,
    invoices,
    plans,
    products,
    quotation_templates,
    quotations,
    subscriptions,
    taxes,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users (admin)"])
api_router.include_router(customers.router, prefix="/customers", tags=["Customers"])
api_router.include_router(taxes.router, prefix="/taxes", tags=["Taxes"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(plans.router, prefix="/plans", tags=["Plans"])
api_router.include_router(
    quotation_templates.router, prefix="/quotation-templates", tags=["Quotation templates"]
)
api_router.include_router(quotations.router, prefix="/quotations", tags=["Quotations"])
api_router.include_router(subscriptions.router, prefix="/subscriptions", tags=["Subscriptions"])
api_router.include_router(discounts.router, prefix="/discounts", tags=["Discounts"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["Invoices"])
api_router.include_router(billing.router, prefix="/billing", tags=["Billing"])

from app.api.v1.routes import payments as _payments_routes  # noqa: E402

api_router.include_router(_payments_routes.router, prefix="/payments", tags=["Payments"])


from app.api.v1.routes import reports as _reports_routes  # noqa: E402

api_router.include_router(_reports_routes.router, prefix="/reports", tags=["Reports"])


from app.api.v1.routes import notifications as _notifications_routes  # noqa: E402

api_router.include_router(_notifications_routes.router, prefix="/notifications", tags=["Notifications"])
