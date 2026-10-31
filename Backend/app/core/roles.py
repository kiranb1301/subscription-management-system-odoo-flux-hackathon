ADMIN = "ADMIN"
INTERNAL = "INTERNAL"
CUSTOMER = "CUSTOMER"

ALL_ROLES = (
    (ADMIN, "Full access: catalog, plans, users, reports"),
    (INTERNAL, "Staff: quotations, subscriptions, invoices, payments"),
    (CUSTOMER, "Portal user: own subscriptions, invoices, payments"),
)