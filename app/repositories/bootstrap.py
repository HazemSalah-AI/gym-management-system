from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.models import Permission, Role, User


class BootstrapRepository:
    def __init__(self, db: Session):
        self.db = db

    def lock(self) -> None:
        if self.db.get_bind().dialect.name == "postgresql":
            # Serialize concurrent bootstraps, including first-admin creation.
            self.db.execute(text("SELECT pg_advisory_xact_lock(574921805)"))

    def permissions(self) -> dict[str, Permission]:
        return {row.code: row for row in self.db.scalars(select(Permission))}

    def roles(self) -> dict[str, Role]:
        return {row.name: row for row in self.db.scalars(select(Role).options(selectinload(Role.permissions)))}

    def add(self, row: Permission | Role | User) -> None:
        self.db.add(row)

    def flush(self) -> None:
        self.db.flush()

    def has_admin(self) -> bool:
        return self.db.scalar(select(User.id).join(User.role).where(Role.name == "Admin").limit(1)) is not None

    def identity_exists(self, username: str, email: str) -> bool:
        return (
            self.db.scalar(select(User.id).where(or_(User.username == username, User.email == email)).limit(1))
            is not None
        )
