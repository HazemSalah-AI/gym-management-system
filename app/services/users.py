from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import AuthSession, Role, User
from app.schemas.domain import StaffUserInput
from app.services.domain import Conflict, NotFound


class UserAdminService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, values: StaffUserInput) -> User:
        email = str(values.email).strip().lower()
        if self.db.scalar(select(User.id).where(or_(User.username == values.username, User.email == email))):
            raise Conflict("Username or email is already in use")
        role = self.db.scalar(select(Role).where(Role.name == values.role_name))
        if not role:
            raise NotFound("Role not found; run the RBAC seed first")
        user = User(username=values.username, email=email, password_hash=hash_password(values.password), role=role)
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise Conflict("Username or email is already in use") from exc
        self.db.refresh(user)
        return user

    def set_active(self, user_id: int, active: bool, actor_id: int) -> User:
        user = self.db.get(User, user_id)
        if not user:
            raise NotFound("User not found")
        if user.id == actor_id and not active:
            raise Conflict("You cannot deactivate your own account")
        user.is_active = active
        if not active:
            self.db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        self.db.commit()
        return user
