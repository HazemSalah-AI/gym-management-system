from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.csrf import get_csrf_token, validate_csrf_token
from app.db.session import get_db
from app.models import User
from app.schemas.auth import CsrfResponse, LoginRequest, UserResponse
from app.services.auth import AuthService, InvalidCredentials

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/csrf", response_model=CsrfResponse)
def csrf(request: Request):
    return CsrfResponse(csrf_token=get_csrf_token(request))


@router.post("/login", response_model=UserResponse, dependencies=[Depends(validate_csrf_token)])
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    previous_token = request.session.get("session_token")
    try:
        user, token = AuthService(db).login(
            payload.username,
            payload.password.get_secret_value(),
            previous_token if isinstance(previous_token, str) else None,
        )
    except InvalidCredentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password") from None
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["session_token"] = token
    get_csrf_token(request)  # Rotate CSRF on successful login; client fetches a fresh token.
    return UserResponse.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(validate_csrf_token)])
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.session.get("session_token")
    AuthService(db).logout(token if isinstance(token, str) else None)
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)
