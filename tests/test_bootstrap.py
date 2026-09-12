import getpass
import secrets
import warnings

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.permissions import PERMISSIONS, ROLE_PERMISSIONS
from app.core.security import verify_password
from app.models import Permission, Role, User, role_permissions
from app.schemas.auth import AdminInput
from app.services.bootstrap import BootstrapConflict, create_first_admin, seed_auth
from scripts import bootstrap_auth


def test_seed_is_idempotent_and_matches_matrix(db):
    seed_auth(db)
    first_ids = {p.code: p.id for p in db.scalars(select(Permission))}
    seed_auth(db)
    assert {p.code: p.id for p in db.scalars(select(Permission))} == first_ids
    assert db.scalar(select(func.count()).select_from(Permission)) == len(PERMISSIONS)
    assert db.scalar(select(func.count()).select_from(Role)) == 4
    assert db.scalar(select(func.count()).select_from(role_permissions)) == sum(map(len, ROLE_PERMISSIONS.values()))
    for role in db.scalars(select(Role)):
        assert {p.code for p in role.permissions} == ROLE_PERMISSIONS[role.name]


def test_seed_corrects_managed_grants_and_preserves_custom_permissions(db):
    seed_auth(db)
    trainer = db.scalar(select(Role).where(Role.name == "Trainer"))
    custom = Permission(code="custom.read", description="Custom permission")
    trainer.permissions = [custom, db.scalar(select(Permission).where(Permission.code == "users.manage"))]
    db.commit()
    seed_auth(db)
    db.refresh(trainer)
    assert {p.code for p in trainer.permissions} == ROLE_PERMISSIONS["Trainer"] | {"custom.read"}


def test_first_admin_hashed_normalized_and_not_overwritten(db, credential):
    seed_auth(db)
    values = AdminInput(username="  Hazem  ", email="  HAZEM@EXAMPLE.COM ", password=credential[0])
    user_id = create_first_admin(db, values)
    user = db.get(User, user_id)
    assert user.username == "hazem" and user.email == "hazem@example.com"
    assert user.password_hash != credential[0]
    assert verify_password(credential[0], user.password_hash)
    original_hash = user.password_hash
    with pytest.raises(BootstrapConflict):
        create_first_admin(db, AdminInput(username="other", email="other@example.com", password=secrets.token_urlsafe(24)))
    db.refresh(user)
    assert user.password_hash == original_hash
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_bootstrap_never_promotes_existing_nonadmin(db, credential):
    seed_auth(db)
    trainer = db.scalar(select(Role).where(Role.name == "Trainer"))
    user = User(username="occupied", email="occupied@example.com", password_hash=credential[1], role=trainer)
    db.add(user)
    db.commit()
    with pytest.raises(BootstrapConflict):
        create_first_admin(db, AdminInput(username="occupied", email="new@example.com", password=credential[0]))
    db.refresh(user)
    assert user.role.name == "Trainer"


@pytest.mark.parametrize("field,value", [("username", "x"), ("email", "invalid"), ("password", "")])
def test_admin_validation(field, value, credential):
    values = {"username": "staff", "email": "staff@example.com", "password": credential[0]}
    values[field] = value
    with pytest.raises(ValidationError):
        AdminInput(**values)


def test_cli_seed_only_idempotent_without_admin(engine, db, monkeypatch, capsys):
    monkeypatch.setattr(bootstrap_auth, "SessionLocal", sessionmaker(engine))
    assert bootstrap_auth.main(["--seed-only"]) == 0
    assert bootstrap_auth.main(["--seed-only"]) == 0
    assert db.scalar(select(func.count()).select_from(User)) == 0
    assert "synchronized" in capsys.readouterr().out


def test_cli_admin_secure_input_and_second_run(engine, db, credential, monkeypatch, capsys):
    monkeypatch.setattr(bootstrap_auth, "SessionLocal", sessionmaker(engine))
    fields = iter(["hazem", "hazem@example.com"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(fields))
    monkeypatch.setattr(getpass, "getpass", lambda prompt: credential[0])
    assert bootstrap_auth.main([]) == 0
    assert bootstrap_auth.main([]) == 0
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert credential[0] not in capsys.readouterr().out


def test_cli_aborts_if_password_would_echo(engine, db, monkeypatch, capsys):
    monkeypatch.setattr(bootstrap_auth, "SessionLocal", sessionmaker(engine))
    fields = iter(["hazem", "hazem@example.com"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(fields))
    def insecure_getpass(prompt):
        warnings.warn("No secure terminal", getpass.GetPassWarning)
    monkeypatch.setattr(getpass, "getpass", insecure_getpass)
    assert bootstrap_auth.main([]) == 1
    assert db.scalar(select(func.count()).select_from(User)) == 0
    assert "cancelled" in capsys.readouterr().out


@pytest.mark.parametrize("field", ["username", "email"])
def test_duplicate_identities_enforced_by_database(db, users, credential, field):
    kwargs = {"username": "newuser", "email": "newuser@example.com", "password_hash": credential[1],
              "role_id": db.get(User, users["Admin"]).role_id}
    kwargs[field] = "admin" if field == "username" else "admin@example.com"
    db.add(User(**kwargs))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_duplicate_role_permission_mapping_rejected(db):
    seed_auth(db)
    row = db.execute(select(role_permissions)).first()
    with pytest.raises(IntegrityError):
        db.execute(role_permissions.insert().values(role_id=row.role_id, permission_id=row.permission_id))
        db.commit()
    db.rollback()
