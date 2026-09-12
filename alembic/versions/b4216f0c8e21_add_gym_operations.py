"""add gym operations

Revision ID: b4216f0c8e21
Revises: 6eb7f390a89e
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b4216f0c8e21"
down_revision: Union[str, Sequence[str], None] = "6eb7f390a89e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("member_number", sa.String(30), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("phone", sa.String(30), nullable=False),
        sa.Column("email", sa.String(254)),
        sa.Column("gender", sa.String(10)),
        sa.Column("date_of_birth", sa.Date()),
        sa.Column("address", sa.String(500)),
        sa.Column("registration_date", sa.Date(), nullable=False),
        sa.Column("emergency_contact_name", sa.String(150)),
        sa.Column("emergency_contact_phone", sa.String(30)),
        sa.Column("notes", sa.Text()),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_members_status"),
        sa.CheckConstraint("gender IS NULL OR gender IN ('male', 'female', 'other')", name="ck_members_gender"),
    )
    op.create_index("ix_members_member_number", "members", ["member_number"], unique=True)
    for column in ("full_name", "phone", "email", "registration_date", "status"):
        op.create_index(f"ix_members_{column}", "members", [column])
    op.create_index("ix_members_name_phone", "members", ["full_name", "phone"])

    op.create_table(
        "membership_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("duration_months", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.CheckConstraint("duration_months > 0", name="ck_membership_plans_duration"),
        sa.CheckConstraint("price >= 0", name="ck_membership_plans_price"),
    )
    op.create_index("ix_membership_plans_is_active", "membership_plans", ["is_active"])

    op.create_table(
        "trainers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("phone", sa.String(30), nullable=False),
        sa.Column("email", sa.String(254)),
        sa.Column("specialization", sa.String(150)),
        sa.Column("notes", sa.Text()),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_trainers_status"),
    )
    for column in ("full_name", "phone", "email", "status"):
        op.create_index(f"ix_trainers_{column}", "trainers", [column])

    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("muscle_group", sa.String(100)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
    )
    op.create_index("ix_exercises_name", "exercises", ["name"], unique=True)
    op.create_index("ix_exercises_muscle_group", "exercises", ["muscle_group"])
    op.create_index("ix_exercises_is_active", "exercises", ["is_active"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("membership_plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("original_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("final_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.CheckConstraint("end_date >= start_date", name="ck_subscriptions_dates"),
        sa.CheckConstraint("original_price >= 0", name="ck_subscriptions_original_price"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_subscriptions_discount"),
        sa.CheckConstraint("final_price >= 0", name="ck_subscriptions_final_price"),
        sa.CheckConstraint("status IN ('active', 'cancelled')", name="ck_subscriptions_status"),
    )
    for column in ("member_id", "plan_id", "start_date", "end_date", "status"):
        op.create_index(f"ix_subscriptions_{column}", "subscriptions", [column])
    op.create_index("ix_subscriptions_member_dates", "subscriptions", ["member_id", "start_date", "end_date"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reference_number", sa.String(100), unique=True),
        sa.Column("notes", sa.Text()),
        sa.Column("recorded_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.CheckConstraint("amount > 0", name="ck_payments_positive_amount"),
        sa.CheckConstraint("method IN ('cash', 'card', 'bank_transfer')", name="ck_payments_method"),
    )
    for column in ("member_id", "subscription_id", "paid_at"):
        op.create_index(f"ix_payments_{column}", "payments", [column])
    op.create_index("ix_payments_paid_at_member", "payments", ["paid_at", "member_id"])

    op.create_table(
        "attendance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("notes", sa.String(500)),
        sa.UniqueConstraint("member_id", "attendance_date", name="uq_attendance_member_day"),
    )
    op.create_index("ix_attendance_member_id", "attendance", ["member_id"])
    op.create_index("ix_attendance_attendance_date", "attendance", ["attendance_date"])
    op.create_index("ix_attendance_date_checked", "attendance", ["attendance_date", "checked_in_at"])

    op.create_table(
        "trainer_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trainer_id", sa.Integer(), sa.ForeignKey("trainers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_trainer_assignments_dates"),
    )
    op.create_index("ix_trainer_assignments_trainer_id", "trainer_assignments", ["trainer_id"])
    op.create_index("ix_trainer_assignments_member_id", "trainer_assignments", ["member_id"])
    op.create_index(
        "uq_trainer_assignments_active_member",
        "trainer_assignments",
        ["member_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        sqlite_where=sa.text("is_active = 1"),
    )

    op.create_table(
        "workout_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("trainer_id", sa.Integer(), sa.ForeignKey("trainers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date()),
        sa.Column("notes", sa.Text()),
        sa.Column("status", sa.String(12), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_workout_plans_dates"),
        sa.CheckConstraint("status IN ('active', 'completed', 'archived')", name="ck_workout_plans_status"),
    )
    for column in ("member_id", "trainer_id", "status"):
        op.create_index(f"ix_workout_plans_{column}", "workout_plans", [column])

    op.create_table(
        "workout_exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workout_plan_id", sa.Integer(), sa.ForeignKey("workout_plans.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Numeric(8, 2)),
        sa.Column("rest_seconds", sa.Integer()),
        sa.Column("notes", sa.String(500)),
        sa.UniqueConstraint("workout_plan_id", "position", name="uq_workout_exercises_position"),
        sa.CheckConstraint("sets > 0", name="ck_workout_exercises_sets"),
        sa.CheckConstraint("reps > 0", name="ck_workout_exercises_reps"),
        sa.CheckConstraint("weight IS NULL OR weight >= 0", name="ck_workout_exercises_weight"),
        sa.CheckConstraint("rest_seconds IS NULL OR rest_seconds >= 0", name="ck_workout_exercises_rest"),
    )
    op.create_index("ix_workout_exercises_workout_plan_id", "workout_exercises", ["workout_plan_id"])
    op.create_index("ix_workout_exercises_exercise_id", "workout_exercises", ["exercise_id"])


def downgrade() -> None:
    for table in (
        "workout_exercises",
        "workout_plans",
        "trainer_assignments",
        "attendance",
        "payments",
        "subscriptions",
        "exercises",
        "trainers",
        "membership_plans",
        "members",
    ):
        op.drop_table(table)
