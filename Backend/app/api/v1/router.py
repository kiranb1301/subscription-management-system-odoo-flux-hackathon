from fastapi import APIRouter

from app.api.v1.routes import (
    auth,
    customers,
    health,
    plans,
    products,
    quotation_templates,
    quotations,
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