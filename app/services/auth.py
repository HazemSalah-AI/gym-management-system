import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import SESSION_MAX_AGE, hash_password, hash_session_token, verify_password
from app.models import User
from app.repositories.auth_session import AuthSessionRepository
from app.repositories.user import UserRepository

# One real Argon2 check even for unknown accounts; no usable default credential.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


class InvalidCredentials(Exception):
    pass


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.sessions = AuthSessionRepository(db)

    def login(self, username: str, password: str, previous_token: str | None = None) -> tuple[User, str]:
        user = self.users.get_by_username(username.strip().lower())
        verified = verify_password(password, user.password_hash if user else _DUMMY_HASH)
        if user is None or not user.is_active or not verified:
            raise InvalidCredentials

        now = datetime.now(timezone.utc)
        token = secrets.token_urlsafe(32)
        try:
            if previous_token:
                self.sessions.delete_token(hash_session_token(previous_token))
            self.sessions.delete_expired(now)
            user.last_login_at = now
            self.sessions.add(hash_session_token(token), user.id, now + timedelta(seconds=SESSION_MAX_AGE))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return user, token

    def current_user(self, user_id: int, token: str) -> User | None:
        now = datetime.now(timezone.utc)
        if self.sessions.get_valid(hash_session_token(token), user_id, now) is None:
            return None
        user = self.users.get_by_id(user_id)
        if user is None or not user.is_active:
            try:
                self.sessions.delete_for_user(user_id)
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            return None
        return user

    def logout(self, token: str | None) -> None:
        if token:
            try:
                self.sessions.delete_token(hash_session_token(token))
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
