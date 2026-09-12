import pytest
from sqlalchemy import select

from app.models import Permission, Role, User


@pytest.mark.parametrize("username,expected", [("admin", 200), ("receptionist", 403), ("trainer", 403), ("owner", 403)])
def test_backend_permission_checks(client, login, username, expected):
    assert login(username).status_code == 200
    assert client.get("/_test/users").status_code == expected


def test_role_change_is_effective_without_relogin(client, login, db, users):
    login()
    assert client.get("/_test/users").status_code == 200
    user = db.get(User, users["Admin"])
    user.role = db.scalar(select(Role).where(Role.name == "Trainer"))
    db.commit()
    assert client.get("/_test/users").status_code == 403


def test_permission_change_is_effective_without_relogin(client, login, db):
    login("trainer")
    assert client.get("/_test/users").status_code == 403
    trainer = db.scalar(select(Role).where(Role.name == "Trainer"))
    trainer.permissions.append(db.scalar(select(Permission).where(Permission.code == "users.manage")))
    db.commit()
    assert client.get("/_test/users").status_code == 200


def test_state_changing_permission_probe_requires_csrf(client, login):
    login("trainer")
    assert client.post("/_test/attendance").status_code == 403
    token = client.get("/auth/csrf").json()["csrf_token"]
    assert client.post("/_test/attendance", headers={"X-CSRF-Token": token}).status_code == 200
