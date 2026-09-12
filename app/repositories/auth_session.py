from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AuthSession


class AuthSessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_valid(self, token_hash: str, user_id: int, now: datetime) -> AuthSession | None:
        return self.db.scalar(select(AuthSession).where(
            AuthSession.token_hash == token_hash,
            AuthSession.user_id == user_id,
            AuthSession.expires_at > now,
        ))

    def add(self, token_hash: str, user_id: int, expires_at: datetime) -> None:
        self.db.add(AuthSession(token_hash=token_hash, user_id=user_id, expires_at=expires_at))

    def delete_token(self, token_hash: str) -> None:
        self.db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash))

    def delete_for_user(self, user_id: int) -> None:
        self.db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))

    def delete_expired(self, now: datetime) -> None:
        self.db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
