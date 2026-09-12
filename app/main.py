from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.core.config import settings
from app.core.security import SESSION_MAX_AGE


app = FastAPI(
    title=settings.app_name
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key.get_secret_value(),
    session_cookie="gym_session",
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=settings.session_https_only,
)


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request: Request, exc: RequestValidationError):
    # Pydantic's default errors can echo submitted passwords or the whole body.
    errors = [{key: error[key] for key in ("type", "loc", "msg")} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.middleware("http")
async def auth_no_store(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/auth" or request.url.path.startswith("/auth/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(health_router)
app.include_router(auth_router)
