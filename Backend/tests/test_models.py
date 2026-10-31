from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import configure_mappers

import app.models  # noqa: F401
from app.db.base import Base

EXPECTED_TABLES = {
    "roles", "users", "password_reset_tokens", "email_verification_tokens",
    "customers", "customer_addresses",
    "products", "product_variants", "product_variant_options",
    "plans", "plan_products", "taxes", "product_taxes",
    "quotation_templates", "quotation_template_lines", "quotations", "quotation_lines",
    "subscriptions", "subscription_lines", "subscription_status_history",
    "discounts", "discount_product_mappings", "discount_usages",
    "invoices", "invoice_lines", "invoice_status_history",
    "payments", "payment_allocations",
    "notifications", "billing_jobs", "audit_logs",
}


def test_all_tables_registered():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_mappers_and_schema_build():
    configure_mappers()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())