from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Role, User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _query():
        return select(User).options(selectinload(User.role).selectinload(Role.permissions))

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.scalar(self._query().where(User.id == user_id))

    def get_by_username(self, username: str) -> User | None:
        return self.db.scalar(self._query().where(User.username == username))
