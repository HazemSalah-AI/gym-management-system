# Gym Management System

Single-gym FastAPI MVP using synchronous SQLAlchemy, Alembic and PostgreSQL.

Phase 5 implementation is present. See `PHASE5_REPORT.md` for the task checklist,
verified results and remaining Docker/PostgreSQL/real-admin checks. No frontend,
public signup, online payments or AI were added.

## Install and configure

Python 3.13 is used by the existing Dockerfile. Development checks in the
implementation environment ran on Python 3.12.14.

```bash
python -m pip install -r requirements-dev.txt
```

Use `.env.example` as a reference. **Keep your existing `.env`** when applying
this update. It must contain `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`,
`POSTGRES_HOST`, `POSTGRES_PORT`, `SECRET_KEY` and `ENVIRONMENT`.

The new Compose file reads credentials from `.env`. For an existing database
volume, use that database's CURRENT username/password/database name. Changing
`POSTGRES_PASSWORD` in Compose does not change the password inside an already
initialized PostgreSQL volume. Do not delete volumes to resolve a mismatch.

Generate a fresh session secret directly into your existing local `.env`
without printing it (run once; this invalidates all earlier signed cookies):

```bash
python -c 'from dotenv import set_key; import secrets; set_key(".env", "SECRET_KEY", secrets.token_urlsafe(48))'
```

No `.env` is included in the delivered archive. Environment secrets belong only
in your local ignored environment file or a deployment secret store. Admin
passwords are entered only through `getpass`, never in `.env` or CLI arguments.

`ENVIRONMENT=development` allows local HTTP. `ENVIRONMENT=production` forces
Secure cookies; serve the application over HTTPS. Unknown environment values
and weak/placeholder session secrets fail validation. Keep proxy/access logs
free of request bodies and cookie/header values.

## Docker startup and database migration

Run from the ORIGINAL project folder after copying in the updated source, so
Compose continues to use the existing project name and `postgres_data` volume.
The database container is healthy before the web container starts.

```bash
docker compose build web
docker compose up -d
docker compose exec web alembic upgrade head
docker compose exec web alembic current
docker compose exec web alembic check
docker compose exec web python -m scripts.bootstrap_auth --seed-only
docker compose exec web python -m scripts.bootstrap_auth
```

The last command asks for username, email and a password of 12–1024 characters,
with hidden confirmation. Do not send that password in chat. Re-running bootstrap
synchronizes built-in RBAC and leaves an existing Admin unchanged. It never
promotes an existing non-admin account or resets an existing password.

The seed owns the seven built-in grants on the four built-in roles; changing
these grants in the database is reversed on the next bootstrap. Custom roles
and custom permission codes are preserved. PostgreSQL advisory locking and
uniqueness constraints protect concurrent first-admin bootstraps.

Local execution without Docker uses `POSTGRES_HOST=localhost`:

```bash
alembic upgrade head
python -m scripts.bootstrap_auth
uvicorn app.main:app --reload
```

## API and CSRF flow

| Method | Path | Request | Success |
| --- | --- | --- | --- |
| GET | `/auth/csrf` | Browser's cookie jar | `200 {"csrf_token": "..."}` |
| POST | `/auth/login` | JSON `username`, `password`; `X-CSRF-Token` header | 200 safe user fields |
| GET | `/auth/me` | Session cookie | 200 safe user fields |
| POST | `/auth/logout` | Cookie and current `X-CSRF-Token` | 204, revokes session |

1. GET `/auth/csrf` and retain the `gym_session` cookie.
2. POST `/auth/login` with that cookie and the returned token in `X-CSRF-Token`.
3. Login rotates both the session token and CSRF token. GET `/auth/csrf` again
   before the next state-changing request.
4. GET `/auth/me` with the cookie to identify the current user.
5. POST `/auth/logout` with the current CSRF token, then `/auth/me` returns 401.

Browser fetch calls use `credentials: "same-origin"`. Keep the frontend and API
on the same origin for this MVP; cross-origin credentials/CORS were not enabled.
Swagger can exercise these JSON routes: first get the token, then explicitly
supply the `X-CSRF-Token` header using a client that allows it. The secure manual
verification script below is simpler and handles the cookie/token flow for you.

Invalid credentials, including inactive accounts, return exactly
`401 {"detail": "Invalid username or password"}`. Missing/invalid authentication
is 401; an authenticated user without permission is 403. Missing/invalid CSRF is
403. Invalid request shape is 422 with input values removed from error output.
Authentication responses use `Cache-Control: no-store`.

## Authentication and sessions

Argon2id hashes passwords with independently generated salts. The service runs
a dummy Argon2 verification for unknown usernames to reduce timing differences.
Username and email are stored lowercase; database checks and unique indexes
prevent case variants from creating separate identities. Username login trims
whitespace and ignores case. There is no public user-creation endpoint.

Starlette SessionMiddleware signs the cookie; it does NOT encrypt it or itself
provide server-side revocation. The cookie contains only `user_id`, an opaque
`session_token`, and `csrf_token`. Never put roles, permissions or password
information in that cookie.

The additional `auth_sessions` table stores only the SHA-256 digest of the random
session token, user reference and timestamps. The server verifies that record,
its absolute eight-hour expiry, the user's existence and active flag on every
protected request. Cookie renewal cannot extend the database expiry. Logout
removes the record, so replaying the old signed cookie does not log back in.
Re-login revokes the previous browser session and creates a fresh one.

When an inactive user is observed, all their session records are revoked. Future
account-deactivation/password-reset services should revoke all sessions in the
same transaction as the account change. Expired rows are cleaned on successful
login. No automatic admin creation or database migration runs at app startup.

Cookies use `HttpOnly`, `SameSite=Lax`, a host-only scope, `/` path and a maximum
age of 28,800 seconds; production adds `Secure`. CSRF uses cryptographic random
tokens and constant-time comparison, including protection on login and logout.

## Permission matrix

The source of truth for built-in grants is `app/core/permissions.py`.
Owner is intentionally a read-only business role in this initial matrix.

| Permission | Admin | Receptionist | Trainer | Owner |
| --- | --- | --- | --- | --- |
| members.read | Yes | Yes | Yes | Yes |
| members.write | Yes | Yes | No | No |
| payments.read | Yes | Yes | No | Yes |
| payments.write | Yes | Yes | No | No |
| attendance.record | Yes | Yes | Yes | No |
| users.manage | Yes | No | No | No |
| reports.read | Yes | No | No | Yes |

Future routes should declare permission dependencies and, for state changes,
CSRF dependencies. Example (illustration only, not a new business endpoint):

```python
@router.post(
    "/attendance",
    dependencies=[
        Depends(require_permission("attendance.record")),
        Depends(validate_csrf_token),
    ],
)
def record_attendance(...):
    ...
```

User -> Role -> Permissions are loaded from the database using `selectinload`.
Database changes take effect on the next request. Test-only protected routes
exist solely in the test suite; they are not registered by `app.main`.

## Tests and manual verification

```bash
python -m pytest -q
python -m scripts.verify_auth
```

The second command talks to `http://localhost:8000`, asks securely for credentials,
and checks CSRF, login, `/auth/me`, logout and wrong-password behavior without
writing cookies or credentials to files.

Default automated tests use a fresh migrated in-memory SQLite database with
foreign keys enabled. To run the same suite against PostgreSQL using your local
`.env` credentials, use Git Bash:

```bash
GYM_TEST_POSTGRES=1 python -m pytest -q
```

This opt-in creates and later drops randomly named `phase5_test_...` schemas in
the configured database. It never uses existing application tables; the database
role must be allowed to create schemas. Each test has its own schema. Do not set
`GYM_TEST_POSTGRES` unless that temporary schema creation is intended.

Inspect the real database without printing credential values:

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d users"'
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d role_permissions"'
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT id, username, role_id, is_active FROM users;"'
```

## Architecture

- `app/models`: database tables and relationships.
- `app/repositories`: database reads/writes, no HTTP or authentication decisions.
- `app/services`: password verification, active-user/session rules and transactions.
- `app/api/dependencies.py`: current-user resolution and reusable permission checks.
- `app/api/routes/auth.py`: HTTP input, CSRF dependencies, cookie state and responses.
- `app/schemas/auth.py`: explicit input and safe output schemas.
- `app/core`: settings, hashing, CSRF and the central permission matrix.
- `scripts`: explicit secure bootstrap and manual API verification.

References: [pwdlib API](https://frankie567.github.io/pwdlib/reference/pwdlib/),
[SQLAlchemy relationship loading](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html).
