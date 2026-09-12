from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.services.auth import AuthService


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    token = request.session.get("session_token")
    # Reject booleans, invalid IDs and oversized/tampered identity fields.
    if type(user_id) is not int or not 0 < user_id <= 2147483647 or not isinstance(token, str) or len(token) != 43:
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user = AuthService(db).current_user(user_id, token)
    if user is None:
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


def require_permission(permission_code: str):
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role is None or not any(
            permission.code == permission_code for permission in current_user.role.permissions
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission denied")
        return current_user

    return dependency
