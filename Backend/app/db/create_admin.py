import getpass

from sqlalchemy import select

from app.core import roles
from app.core.security import hash_password
from app.db.seed import seed_roles
from app.db.session import SessionLocal
from app.models import Role, User
from app.schemas.auth import RegisterRequest


def main() -> None:
    full_name = input("Full name: ").strip()
    email = input("Email: ").strip().lower()
    password = getpass.getpass("Password: ")

    # Reuse the same password rules as registration
    RegisterRequest(full_name=full_name, email=email, password=password)

    with SessionLocal() as db:
        seed_roles(db)
        if db.scalar(select(User).where(User.email == email)):
            print("A user with this email already exists.")
            return
        admin_role = db.scalar(select(Role).where(Role.name == roles.ADMIN))
        db.add(
            User(
                full_name=full_name,
                email=email,
                password_hash=hash_password(password),
                role_id=admin_role.id,
                is_email_verified=True,
            )
        )
        db.commit()
    print(f"Admin created: {email}")


if __name__ == "__main__":
    main()