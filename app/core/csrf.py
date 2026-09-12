import hmac
import secrets

from fastapi import HTTPException, Request, status


def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not isinstance(token, str) or len(token) != 43:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def validate_csrf_token(request: Request) -> None:
    expected = request.session.get("csrf_token")
    supplied = request.headers.get("X-CSRF-Token")
    if (
        not isinstance(expected, str)
        or not isinstance(supplied, str)
        or len(supplied) != 43
        or not hmac.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8"))
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or missing CSRF token")


def validate_csrf_value(request: Request, supplied: str | None) -> None:
    """Validate a token submitted by an HTML form."""
    expected = request.session.get("csrf_token")
    if (
        not isinstance(expected, str)
        or not isinstance(supplied, str)
        or len(supplied) != 43
        or not hmac.compare_digest(expected.encode(), supplied.encode())
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or missing CSRF token")
