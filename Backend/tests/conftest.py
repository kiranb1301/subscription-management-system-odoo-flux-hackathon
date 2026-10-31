import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.security import hash_password
from app.db.base import Base
from app.db.seed import seed_roles
from app.db.session import get_db
from app.main import app as fastapi_app
from app.models import Role, User


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db:
        seed_roles(db)
    yield factory
    Base.metadata.drop_all(engine)


@pytest.fixture()
def api(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


@pytest.fixture()
def make_staff(session_factory):
    """Create an ADMIN or INTERNAL user directly in the test database."""

    def _make(email: str, role: str, password: str = "Strong#Pass1") -> str:
        with session_factory() as db:
            role_row = db.query(Role).filter_by(name=role).one()
            db.add(
                User(
                    full_name=f"{role.title()} User",
                    email=email,
                    password_hash=hash_password(password),
                    role_id=role_row.id,
                    is_email_verified=True,
                )
            )
            db.commit()
        return password

    return _make