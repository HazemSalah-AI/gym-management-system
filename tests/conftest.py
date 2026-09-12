"""Tests use a fresh migrated database per test; never touch the gym database.

Default: SQLite with foreign keys enabled.
GYM_TEST_POSTGRES=1: use .env PostgreSQL credentials, but create/drop only a
random test schema. The connection role needs CREATE permission on the database.
"""
import os
import secrets

USE_POSTGRES = os.environ.get("GYM_TEST_POSTGRES") == "1"
os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
if not USE_POSTGRES:
    os.environ.update(
        ENVIRONMENT="test", POSTGRES_USER="phase5_test",
        POSTGRES_PASSWORD=secrets.token_urlsafe(24), POSTGRES_DB="phase5_test",
    )

import pytest
from alembic import command
from alembic.config import Config
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import require_permission
from app.core.config import settings
from app.core.csrf import validate_csrf_token
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import User
from app.services.bootstrap import seed_auth
from app.repositories.bootstrap import BootstrapRepository


# Test-only probes. These are never registered by production app imports.
@app.get("/_test/users", dependencies=[Depends(require_permission("users.manage"))])
def protected_users():
    return {"allowed": True}


@app.post("/_test/attendance", dependencies=[
    Depends(require_permission("attendance.record")), Depends(validate_csrf_token),
])
def protected_attendance():
    return {"recorded": True}


@pytest.fixture
def engine():
    schema = "phase5_test_" + secrets.token_hex(12)
    admin_engine = None
    if USE_POSTGRES:
        admin_engine = create_engine(settings.database_url, hide_parameters=True)
        with admin_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        db_engine = create_engine(settings.database_url, hide_parameters=True)

        @event.listens_for(db_engine, "connect")
        def set_schema(connection, record):
            original = connection.autocommit
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(f'SET search_path TO "{schema}"')
            connection.autocommit = original
    else:
        db_engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool, hide_parameters=True,
        )

        @event.listens_for(db_engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

    try:
        with db_engine.begin() as conn:
            cfg = Config("alembic.ini")
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
        yield db_engine
    finally:
        db_engine.dispose()
        if admin_engine:
            # Only the schema created above, never existing gym tables/volumes.
            with admin_engine.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin_engine.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(scope="session")
def credential():
    password = secrets.token_urlsafe(24)
    return password, hash_password(password)


@pytest.fixture
def users(db, credential):
    seed_auth(db)
    roles = BootstrapRepository(db).roles()
    ids = {}
    for name, role in roles.items():
        user = User(username=name.lower(), email=f"{name.lower()}@example.com",
                    password_hash=credential[1], role=role)
        db.add(user)
        db.flush()
        ids[name] = user.id
    db.commit()
    return ids


@pytest.fixture
def client(engine):
    def override_db():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = override_db
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def login(client, users, credential):
    def perform(username="admin"):
        csrf = client.get("/auth/csrf").json()["csrf_token"]
        return client.post("/auth/login", json={"username": username, "password": credential[0]},
                           headers={"X-CSRF-Token": csrf})
    return perform
