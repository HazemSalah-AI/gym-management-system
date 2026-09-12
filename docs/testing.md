# Testing

Run the complete local gate:

```bash
python -m ruff check app tests scripts alembic
python -m pytest -q
python -c "from app.main import app; assert app.title"
```

The test suite covers authentication, session revocation, CSRF, role changes, member workflows, calendar-month renewals, price snapshots, discounts, partial/full/invalid payments, attendance eligibility, same-day uniqueness, trainer-assignment history, workout ordering, reporting authorization and Alembic drift.

SQLite is used for fast isolated tests. Set `GYM_TEST_POSTGRES=1` to make each test use a randomly named schema in PostgreSQL; this mode verifies PostgreSQL constraints and is used by CI.

Do not point tests at production. PostgreSQL mode creates and drops schemas and requires an account with schema-creation permission.
