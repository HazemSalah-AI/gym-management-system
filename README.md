# Gym Management System

A production-oriented, single-gym management MVP built with FastAPI, SQLAlchemy,
PostgreSQL, Alembic, Jinja2, Bootstrap and vanilla JavaScript. It provides a
responsive browser UI and permission-protected JSON endpoints for daily gym
operations.

## Features

- Revocable cookie sessions, Argon2id password hashing, CSRF protection and database-backed RBAC.
- Member creation, editing, searching, filtering, pagination and reversible deactivation.
- Configurable calendar-month membership plans, subscription history, renewal without lost paid days and price snapshots.
- Auditable cash/card/bank-transfer payment recording, partial payments and derived balances with overpayment protection.
- Egypt-local attendance dates, active-subscription checks and one check-in per member per day.
- Trainers, historical member assignments, reusable exercises and ordered workout-plan exercises.
- SQL-aggregate dashboard metrics, filtered business reports and UTF-8 CSV exports.
- Responsive server-rendered administration UI, production Docker image and PostgreSQL CI.

Online payments, member accounts, multi-branch tenancy, biometrics, messaging and AI are intentionally outside this MVP.

## Architecture

The application is a modular monolith:

```text
Browser / API client -> FastAPI routes -> services -> repositories -> SQLAlchemy -> PostgreSQL
```

- `app/api/routes`: HTTP, form parsing, rendering and response semantics.
- `app/services`: business rules and transaction coordination.
- `app/repositories`: database queries, filters, pagination and aggregates.
- `app/models`: normalized persistence schema and constraints.
- `app/schemas`: Pydantic input validation.
- `app/templates` and `app/static`: Jinja2/Bootstrap UI.
- `alembic/versions`: reviewed schema history; production never uses `create_all()`.
- `tests`: unit, API, security and migration coverage.

See [architecture](docs/architecture.md), [security](docs/security.md),
[testing](docs/testing.md) and [AWS deployment preparation](docs/aws-deployment.md).

## Roles and permissions

- **Admin:** all operations, staff accounts and settings.
- **Receptionist:** members, memberships, subscriptions, payments, attendance and basic read access.
- **Trainer:** assigned-member visibility, attendance and workout management; no financial access.
- **Owner:** read-oriented dashboard, operations and reports access.

Backend dependencies enforce every permission. Hiding navigation items is only a UX convenience.
The built-in permission matrix is defined in `app/core/permissions.py` and synchronized by the bootstrap command.

## Environment

Copy `.env.example` to an ignored `.env` and fill the values. Never commit `.env`.

| Variable | Purpose |
| --- | --- |
| `APP_NAME` | Display/application name |
| `ENVIRONMENT` | `development`, `test`, or `production` |
| `SECRET_KEY` | Random value of at least 32 characters used to sign session cookies |
| `POSTGRES_*` | PostgreSQL connection components |
| `GYM_TIMEZONE` | IANA gym timezone; defaults to `Africa/Cairo` |
| `SESSION_MAX_AGE` | Absolute session lifetime in seconds, 300–86400 |
| `COOKIE_SECURE` | Override secure-cookie behavior; production should be `true` |
| `ALLOWED_HOSTS` | Comma-separated hostnames accepted by the application |

Generate a development secret without printing it:

```bash
python -c 'from dotenv import set_key; import secrets; set_key(".env", "SECRET_KEY", secrets.token_urlsafe(48))'
```

Production secrets belong in AWS Secrets Manager or SSM Parameter Store, not an image, repository or task definition.

## Local Python setup

Python 3.12+ is supported; the containers use Python 3.13.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
alembic upgrade head
python -m scripts.bootstrap_auth --seed-only
python -m scripts.bootstrap_auth
uvicorn app.main:app --reload
```

On Windows PowerShell activate with `.venv\Scripts\Activate.ps1`. The admin command requests the password through hidden terminal input. It never accepts it as a command-line argument.

Open `http://localhost:8000/login`. Development API documentation is at `/docs`; it is disabled in production.

## Docker development

```bash
docker compose build
docker compose up -d
docker compose exec web alembic upgrade head
docker compose exec web python -m scripts.bootstrap_auth --seed-only
docker compose exec web python -m scripts.bootstrap_auth
docker compose logs -f web
docker compose exec web python -m pytest -q
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose down
```

`docker compose down -v` permanently removes the local PostgreSQL volume. Do not use `-v` unless deleting local data is intentional.

## Migrations

```bash
alembic current
alembic heads
alembic upgrade head
alembic check
```

For a new schema change, update the models, generate a revision, inspect every operation, test upgrade/downgrade in an isolated database, and commit model and migration together. Never run destructive migration experiments against production data.

## Testing and linting

```bash
python -m ruff check app tests scripts alembic
python -m pytest -q
```

Default tests use a fresh migrated in-memory SQLite database. Important PostgreSQL integration behavior can be verified in isolated, randomly named schemas:

```bash
GYM_TEST_POSTGRES=1 python -m pytest -q
```

The configured role must be able to create/drop test schemas. The test fixture never uses existing application tables. CI runs this PostgreSQL mode and builds the production image.

## Production container

The main `Dockerfile` runs as a non-root user, uses two Uvicorn workers without reload and includes a health check.

```bash
docker build -t gym-management-system:latest .
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec web alembic upgrade head
```

Run migrations as a one-off deployment step before replacing the application tasks. Do not run concurrent automatic migrations from every worker.

## Security and operations

- Production cookies are `HttpOnly`, `Secure` and `SameSite=Lax`; sessions have server-side revocation records.
- Every state-changing browser/API request requires a server-validated CSRF token.
- Trusted-host validation, content/type/frame/referrer/permissions policies and production HSTS are enabled.
- Validation errors omit submitted values, and secrets are hidden from SQLAlchemy diagnostics.
- Members, users, plans and trainers are deactivated rather than hard-deleted; financial history is immutable in the MVP.
- Back up RDS automatically, enable deletion protection and test restore procedures before launch.

## AWS deployment preparation

The recommended MVP architecture is ALB + ECS Fargate + RDS PostgreSQL, with images in ECR, TLS from ACM, DNS in Route 53, logs in CloudWatch and runtime secrets from Secrets Manager. No Kubernetes is required.

Follow [docs/aws-deployment.md](docs/aws-deployment.md) for the exact checklist, networking, IAM, migration, backup and rollback procedures.

**No AWS resources are created by this repository and no AWS deployment has been performed.**
