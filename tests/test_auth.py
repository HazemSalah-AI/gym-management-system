import base64
import json
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select, update

from app.models import AuthSession, User


def test_health_and_registered_routes(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/db").json()["database"] == "connected"
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/auth/csrf", "/auth/login", "/auth/logout", "/auth/me"} <= set(paths)


def test_login_me_cookie_and_safe_serialization(client, login, db, users):
    response = login()
    assert response.status_code == 200
    assert response.json()["id"] == users["Admin"]
    assert response.json()["last_login_at"] is not None
    cookie = response.headers["set-cookie"].lower()
    assert "gym_session=" in cookie and "httponly" in cookie
    assert "samesite=lax" in cookie and "max-age=28800" in cookie
    assert response.headers["cache-control"] == "no-store"
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert set(me.json()) == {"id", "username", "email", "is_active", "role", "last_login_at"}
    payload = json.loads(base64.b64decode(client.cookies.get("gym_session").split(".")[0]))
    assert set(payload) == {"user_id", "session_token", "csrf_token"}
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 1
    record = db.scalar(select(AuthSession))
    assert record.token_hash != payload["session_token"]
    assert len(record.token_hash) == 64


@pytest.mark.parametrize("username", ["admin", "unknown"])
def test_wrong_credentials_share_public_error(client, users, username):
    token = client.get("/auth/csrf").json()["csrf_token"]
    response = client.post("/auth/login", json={"username": username, "password": secrets.token_urlsafe(24)},
                           headers={"X-CSRF-Token": token})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}
    assert client.get("/auth/me").status_code == 401


def test_username_login_normalized(login):
    assert login("  ADMIN  ").status_code == 200


def test_inactive_login_has_generic_error(client, login, db, users):
    db.execute(update(User).where(User.id == users["Admin"]).values(is_active=False))
    db.commit()
    response = login()
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


@pytest.mark.parametrize("method,path", [("get", "/auth/me"), ("get", "/_test/users"), ("post", "/_test/attendance")])
def test_no_authentication_is_401(client, method, path):
    assert getattr(client, method)(path).status_code == 401


@pytest.mark.parametrize("token", [None, "incorrect", "é" * 43])
def test_login_csrf_rejected(client, users, credential, token):
    client.get("/auth/csrf")
    response = client.post("/auth/login", json={"username": "admin", "password": credential[0]},
                           headers={} if token is None else {"X-CSRF-Token": token.encode("utf-8")})
    assert response.status_code == 403


def test_csrf_from_other_session_is_rejected(client, credential):
    token = client.get("/auth/csrf").json()["csrf_token"]
    client.cookies.clear()
    client.get("/auth/csrf")
    assert client.post("/auth/login", json={"username": "admin", "password": credential[0]},
                       headers={"X-CSRF-Token": token}).status_code == 403


def test_csrf_rotates_at_login(client, login):
    old = client.get("/auth/csrf").json()["csrf_token"]
    assert login().status_code == 200
    new = client.get("/auth/csrf").json()["csrf_token"]
    assert new != old
    assert client.post("/auth/logout", headers={"X-CSRF-Token": old}).status_code == 403
    assert client.get("/auth/me").status_code == 200


def test_logout_revokes_replayed_cookie(client, login, db):
    login()
    saved_cookie = client.cookies.get("gym_session")
    token = client.get("/auth/csrf").json()["csrf_token"]
    assert client.post("/auth/logout", headers={"X-CSRF-Token": token}).status_code == 204
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
    assert client.get("/auth/me").status_code == 401
    client.cookies.set("gym_session", saved_cookie)
    assert client.get("/auth/me").status_code == 401


def test_logout_requires_csrf(client, login):
    login()
    assert client.post("/auth/logout").status_code == 403
    assert client.get("/auth/me").status_code == 200


def test_inactive_user_clears_session_and_revokes_all(client, login, db, users):
    login()
    old = client.cookies.get("gym_session")
    db.execute(update(User).where(User.id == users["Admin"]).values(is_active=False))
    db.commit()
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert "expires=thu, 01 jan 1970" in response.headers["set-cookie"].lower()
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
    db.execute(update(User).where(User.id == users["Admin"]).values(is_active=True))
    db.commit()
    client.cookies.set("gym_session", old)
    assert client.get("/auth/me").status_code == 401


def test_deleted_user_invalidates_session(client, login, db, users):
    login()
    db.execute(delete(User).where(User.id == users["Admin"]))
    db.commit()
    assert client.get("/auth/me").status_code == 401
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_absolute_session_expiry(client, login, db):
    login()
    db.execute(update(AuthSession).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    db.commit()
    assert client.get("/auth/me").status_code == 401


def test_relogin_rotates_and_revokes_previous_session(client, login):
    login()
    old = client.cookies.get("gym_session")
    assert login().status_code == 200
    client.cookies.clear()
    client.cookies.set("gym_session", old)
    assert client.get("/auth/me").status_code == 401


def test_tampered_cookie_is_401(client, login):
    login()
    old = client.cookies.get("gym_session")
    client.cookies.clear()
    client.cookies.set("gym_session", "x" + old)
    assert client.get("/auth/me").status_code == 401


def test_validation_does_not_echo_password_or_body(client):
    secret = secrets.token_urlsafe(24)
    token = client.get("/auth/csrf").json()["csrf_token"]
    for payload in ({"password": secret}, {"username": "admin", "password": {"secret": secret}},
                    {"username": "admin", "password": secret, "extra": secret}):
        response = client.post("/auth/login", json=payload, headers={"X-CSRF-Token": token})
        assert response.status_code == 422
        assert secret not in response.text


def test_login_failure_rolls_back_session_and_timestamp(db, users, credential, monkeypatch):
    from app.services.auth import AuthService
    user = db.get(User, users["Admin"])
    assert user.last_login_at is None
    def fail_commit():
        raise RuntimeError("Simulated database failure")
    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(RuntimeError):
        AuthService(db).login("admin", credential[0])
    db.expire_all()
    assert db.get(User, users["Admin"]).last_login_at is None
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
