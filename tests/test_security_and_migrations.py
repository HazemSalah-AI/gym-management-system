import io
import secrets

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import inspect, text
from starlette.middleware.sessions import SessionMiddleware
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.config import Settings
from app.core.security import SESSION_MAX_AGE, hash_password, verify_password


def config_values():
    return dict(_env_file=None, secret_key=secrets.token_urlsafe(48), postgres_user="check",
                postgres_password=secrets.token_urlsafe(24), postgres_db="check")


def test_argon2_passwords(credential):
    assert credential[1].startswith("$argon2id$")
    assert verify_password(credential[0], credential[1])
    assert not verify_password(secrets.token_urlsafe(24), credential[1])
    assert hash_password(credential[0]) != credential[1]


@pytest.mark.parametrize("bad_hash", ["", "broken", "$argon2id$broken"])
def test_malformed_hash_is_safe(bad_hash):
    assert verify_password(secrets.token_urlsafe(24), bad_hash) is False


def test_production_rejects_weak_secret_without_exposing_input():
    values = config_values()
    values.update(environment="production", secret_key=secrets.token_urlsafe(8))
    with pytest.raises(ValidationError) as exc:
        Settings(**values)
    assert values["secret_key"] not in str(exc.value)


def test_unknown_environment_fails_closed():
    with pytest.raises(ValidationError):
        Settings(**config_values(), environment="prodution")


def test_database_url_preserves_special_characters_and_hides_secrets():
    values = config_values()
    values["postgres_password"] = secrets.token_urlsafe(20) + "@:/?#%"
    settings = Settings(**values)
    assert settings.database_url.password == values["postgres_password"]
    assert values["postgres_password"] not in repr(settings)
    assert values["postgres_password"] not in str(settings.database_url)


def test_production_secure_cookie():
    settings = Settings(**config_values(), environment="production")
    assert settings.session_https_only is True
    async def endpoint(request: Request):
        request.session["csrf_token"] = secrets.token_urlsafe(32)
        return JSONResponse({"ok": True})
    app = Starlette(routes=[Route("/", endpoint)])
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key.get_secret_value(),
                       session_cookie="gym_session", max_age=SESSION_MAX_AGE,
                       same_site="lax", https_only=settings.session_https_only)
    with TestClient(app, base_url="https://testserver") as client:
        cookie = client.get("/").headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_migration_schema_constraints_and_no_drift(engine):
    inspector = inspect(engine)
    expected = {"users", "roles", "permissions", "role_permissions", "auth_sessions", "alembic_version"}
    assert set(inspector.get_table_names()) == expected
    indexes = {i["name"]: i for i in inspector.get_indexes("users")}
    assert indexes["ix_users_username"]["unique"]
    assert indexes["ix_users_email"]["unique"]
    assert inspector.get_foreign_keys("users")[0]["referred_table"] == "roles"
    assert set(inspector.get_pk_constraint("role_permissions")["constrained_columns"]) == {"role_id", "permission_id"}
    with engine.begin() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "6eb7f390a89e"
        cfg = Config("alembic.ini")
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        command.current(cfg, check_heads=True)
        command.check(cfg)


def test_migration_downgrade_upgrade_only_in_isolated_test_database(engine):
    with engine.begin() as conn:
        cfg = Config("alembic.ini")
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "1936134f3938")
        assert set(inspect(conn).get_table_names()) == {"alembic_version"}
        command.upgrade(cfg, "head")
        assert "auth_sessions" in inspect(conn).get_table_names()


def test_postgresql_offline_migration_uses_boolean_default_and_no_unrelated_drops():
    output = io.StringIO()
    cfg = Config("alembic.ini", output_buffer=output)
    command.upgrade(cfg, "head", sql=True)
    sql = output.getvalue()
    assert "BOOLEAN DEFAULT true" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "DROP TABLE" not in sql and "DROP COLUMN" not in sql
    for table in ("users", "roles", "permissions", "role_permissions", "auth_sessions"):
        assert f"CREATE TABLE {table}" in sql
