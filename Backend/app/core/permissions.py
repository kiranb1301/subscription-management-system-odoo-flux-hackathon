from app.core import roles

ADMIN_ONLY = (roles.ADMIN,)
STAFF = (roles.ADMIN, roles.INTERNAL)
ANY_ROLE = (roles.ADMIN, roles.INTERNAL, roles.CUSTOMER)


def is_staff(user) -> bool:
    return user.role.name in STAFF