# Architecture

## Scope

This is a single-gym modular monolith. One deployable FastAPI process owns browser pages, JSON endpoints and business workflows. PostgreSQL is the system of record and Alembic is the only production schema-management mechanism.

## Boundaries

1. Routes parse HTTP input, apply authentication/permission dependencies and render or serialize responses.
2. Services enforce renewal, financial, attendance and assignment rules and coordinate transactions.
3. Repositories perform database-side filtering, pagination, eager loading and aggregation.
4. SQLAlchemy models hold persistence relationships and defensive database constraints.

The browser UI and JSON routes call the same services, so financial and eligibility rules cannot be bypassed through a different client.

## Data model decisions

- Subscription prices and discounts are snapshots. Later plan-price changes never rewrite history.
- Remaining balance is derived from the subscription final price minus recorded payments.
- Attendance stores the configured gym-local date plus an aware timestamp. A unique member/date constraint closes concurrent duplicate-check-in races.
- Trainer assignments are historical rows. A filtered unique index allows only one active trainer assignment per member.
- Sets, reps, weight, rest and order live on `workout_exercises`, not the reusable exercise catalog.
- Operational and financial history uses restrictive foreign keys and no casual delete endpoints.

## Future change

The boundaries can support a mobile API or analytics pipeline later. Multi-gym tenancy is deliberately not modeled; adding it requires a reviewed migration and tenant-aware authorization rather than simply adding a UI selector.
