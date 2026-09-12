from sqlalchemy.orm import Session

from app.core.permissions import PERMISSIONS, ROLE_PERMISSIONS
from app.core.security import hash_password
from app.models import Permission, Role, User
from app.repositories.bootstrap import BootstrapRepository
from app.schemas.auth import AdminInput


class BootstrapConflict(Exception):
    pass


def seed_auth(db: Session) -> None:
    """Owns its transaction. Reconcile built-in grants, preserve custom grants."""
    repo = BootstrapRepository(db)
    try:
        repo.lock()
        permissions = repo.permissions()
        for code, description in PERMISSIONS.items():
            if code not in permissions:
                permissions[code] = Permission(code=code, description=description)
                repo.add(permissions[code])
            else:
                permissions[code].description = description
        roles = repo.roles()
        for name, codes in ROLE_PERMISSIONS.items():
            if name not in roles:
                roles[name] = Role(name=name)
                repo.add(roles[name])
            custom = [p for p in roles[name].permissions if p.code not in PERMISSIONS]
            roles[name].permissions = custom + [permissions[code] for code in sorted(codes)]
        db.commit()
    except Exception:
        db.rollback()
        raise


def create_first_admin(db: Session, values: AdminInput) -> int:
    repo = BootstrapRepository(db)
    try:
        repo.lock()
        if repo.has_admin():
            raise BootstrapConflict("An Admin already exists; no account was changed.")
        if repo.identity_exists(values.username, str(values.email)):
            raise BootstrapConflict("Username or email is already in use; no account was changed.")
        admin_role = repo.roles().get("Admin")
        if admin_role is None:
            raise BootstrapConflict("Seed roles before creating the first Admin.")
        user = User(
            username=values.username,
            email=str(values.email),
            password_hash=hash_password(values.password.get_secret_value()),
            role=admin_role,
            is_active=True,
        )
        repo.add(user)
        repo.flush()
        user_id = user.id
        db.commit()
        return user_id
    except Exception:
        db.rollback()
        raise
