from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.roles import ALL_ROLES
from app.db.session import SessionLocal
from app.models import Role


def seed_roles(db: Session) -> None:
    """Idempotent: safe to run any number of times."""
    for name, description in ALL_ROLES:
        if db.scalar(select(Role).where(Role.name == name)) is None:
            db.add(Role(name=name, description=description))
    db.commit()


def main() -> None:
    with SessionLocal() as db:
        seed_roles(db)
    print("Roles seeded: " + ", ".join(name for name, _ in ALL_ROLES))


if __name__ == "__main__":
    main()