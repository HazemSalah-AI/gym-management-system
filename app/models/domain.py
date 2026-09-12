from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Member(TimestampMixin, Base):
    __tablename__ = "members"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="ck_members_status"),
        CheckConstraint("gender IS NULL OR gender IN ('male', 'female', 'other')", name="ck_members_gender"),
        Index("ix_members_name_phone", "full_name", "phone"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150), index=True)
    phone: Mapped[str] = mapped_column(String(30), index=True)
    email: Mapped[str | None] = mapped_column(String(254), index=True)
    gender: Mapped[str | None] = mapped_column(String(10))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    address: Mapped[str | None] = mapped_column(String(500))
    registration_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(150))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(30))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="active", server_default="active", index=True)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="member")
    payments: Mapped[list["Payment"]] = relationship(back_populates="member")
    attendance: Mapped[list["Attendance"]] = relationship(back_populates="member")
    trainer_assignments: Mapped[list["TrainerAssignment"]] = relationship(back_populates="member")
    workout_plans: Mapped[list["WorkoutPlan"]] = relationship(back_populates="member")


class MembershipPlan(TimestampMixin, Base):
    __tablename__ = "membership_plans"
    __table_args__ = (
        CheckConstraint("duration_months > 0", name="ck_membership_plans_duration"),
        CheckConstraint("price >= 0", name="ck_membership_plans_price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    duration_months: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), index=True)
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="plan")


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_subscriptions_dates"),
        CheckConstraint("original_price >= 0", name="ck_subscriptions_original_price"),
        CheckConstraint("discount_amount >= 0", name="ck_subscriptions_discount"),
        CheckConstraint("final_price >= 0", name="ck_subscriptions_final_price"),
        CheckConstraint("status IN ('active', 'cancelled')", name="ck_subscriptions_status"),
        Index("ix_subscriptions_member_dates", "member_id", "start_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("membership_plans.id", ondelete="RESTRICT"), index=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    original_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    final_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(12), default="active", server_default="active", index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    member: Mapped[Member] = relationship(back_populates="subscriptions")
    plan: Mapped[MembershipPlan] = relationship(back_populates="subscriptions")
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_user_id])
    payments: Mapped[list["Payment"]] = relationship(back_populates="subscription")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_positive_amount"),
        CheckConstraint("method IN ('cash', 'card', 'bank_transfer')", name="ck_payments_method"),
        Index("ix_payments_paid_at_member", "paid_at", "member_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"), index=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(20))
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reference_number: Mapped[str | None] = mapped_column(String(100), unique=True)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

    member: Mapped[Member] = relationship(back_populates="payments")
    subscription: Mapped[Subscription] = relationship(back_populates="payments")
    recorded_by: Mapped["User"] = relationship(foreign_keys=[recorded_by_user_id])


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("member_id", "attendance_date", name="uq_attendance_member_day"),
        Index("ix_attendance_date_checked", "attendance_date", "checked_in_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"), index=True)
    attendance_date: Mapped[date] = mapped_column(Date, index=True)
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    notes: Mapped[str | None] = mapped_column(String(500))
    member: Mapped[Member] = relationship(back_populates="attendance")
    recorded_by: Mapped["User"] = relationship(foreign_keys=[recorded_by_user_id])


class Trainer(TimestampMixin, Base):
    __tablename__ = "trainers"
    __table_args__ = (CheckConstraint("status IN ('active', 'inactive')", name="ck_trainers_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150), index=True)
    phone: Mapped[str] = mapped_column(String(30), index=True)
    email: Mapped[str | None] = mapped_column(String(254), index=True)
    specialization: Mapped[str | None] = mapped_column(String(150))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="active", server_default="active", index=True)
    assignments: Mapped[list["TrainerAssignment"]] = relationship(back_populates="trainer")
    workout_plans: Mapped[list["WorkoutPlan"]] = relationship(back_populates="trainer")


class TrainerAssignment(Base):
    __tablename__ = "trainer_assignments"
    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_trainer_assignments_dates"),
        Index(
            "uq_trainer_assignments_active_member",
            "member_id",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_id: Mapped[int] = mapped_column(ForeignKey("trainers.id", ondelete="RESTRICT"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    trainer: Mapped[Trainer] = relationship(back_populates="assignments")
    member: Mapped[Member] = relationship(back_populates="trainer_assignments")


class Exercise(TimestampMixin, Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    muscle_group: Mapped[str | None] = mapped_column(String(100), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), index=True)
    workout_items: Mapped[list["WorkoutExercise"]] = relationship(back_populates="exercise")


class WorkoutPlan(TimestampMixin, Base):
    __tablename__ = "workout_plans"
    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_workout_plans_dates"),
        CheckConstraint("status IN ('active', 'completed', 'archived')", name="ck_workout_plans_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"), index=True)
    trainer_id: Mapped[int] = mapped_column(ForeignKey("trainers.id", ondelete="RESTRICT"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="active", server_default="active", index=True)
    member: Mapped[Member] = relationship(back_populates="workout_plans")
    trainer: Mapped[Trainer] = relationship(back_populates="workout_plans")
    exercises: Mapped[list["WorkoutExercise"]] = relationship(
        back_populates="workout_plan", cascade="all, delete-orphan", order_by="WorkoutExercise.position"
    )


class WorkoutExercise(Base):
    __tablename__ = "workout_exercises"
    __table_args__ = (
        UniqueConstraint("workout_plan_id", "position", name="uq_workout_exercises_position"),
        CheckConstraint("sets > 0", name="ck_workout_exercises_sets"),
        CheckConstraint("reps > 0", name="ck_workout_exercises_reps"),
        CheckConstraint("weight IS NULL OR weight >= 0", name="ck_workout_exercises_weight"),
        CheckConstraint("rest_seconds IS NULL OR rest_seconds >= 0", name="ck_workout_exercises_rest"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_plan_id: Mapped[int] = mapped_column(ForeignKey("workout_plans.id", ondelete="CASCADE"), index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="RESTRICT"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    sets: Mapped[int] = mapped_column(Integer)
    reps: Mapped[int] = mapped_column(Integer)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    rest_seconds: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(String(500))
    workout_plan: Mapped[WorkoutPlan] = relationship(back_populates="exercises")
    exercise: Mapped[Exercise] = relationship(back_populates="workout_items")
