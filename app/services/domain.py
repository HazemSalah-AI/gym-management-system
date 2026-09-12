import calendar
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Attendance,
    Exercise,
    Member,
    MembershipPlan,
    Payment,
    Subscription,
    Trainer,
    TrainerAssignment,
    WorkoutExercise,
    WorkoutPlan,
)
from app.repositories.domain import DomainRepository
from app.schemas.domain import (
    AssignmentInput,
    AttendanceInput,
    ExerciseInput,
    MemberInput,
    PaymentInput,
    PlanInput,
    SubscriptionInput,
    TrainerInput,
    WorkoutExerciseInput,
    WorkoutInput,
)


class DomainError(Exception):
    pass


class NotFound(DomainError):
    pass


class Conflict(DomainError):
    pass


def add_calendar_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def subscription_end_date(start: date, duration_months: int) -> date:
    return add_calendar_months(start, duration_months) - timedelta(days=1)


class DomainService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = DomainRepository(db)

    def _commit(self):
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise Conflict("The requested record conflicts with existing data") from exc

    def create_member(self, values: MemberInput) -> Member:
        member = Member(member_number=f"PENDING-{secrets.token_hex(8)}", **values.model_dump())
        self.db.add(member)
        self.db.flush()
        member.member_number = f"GYM-{member.id:06d}"
        self._commit()
        self.db.refresh(member)
        return member

    def update_member(self, member_id: int, values: MemberInput) -> Member:
        member = self.repo.member(member_id)
        if not member:
            raise NotFound("Member not found")
        for key, value in values.model_dump().items():
            setattr(member, key, value)
        self._commit()
        return member

    def set_member_active(self, member_id: int, active: bool) -> Member:
        member = self.repo.member(member_id)
        if not member:
            raise NotFound("Member not found")
        member.status = "active" if active else "inactive"
        self._commit()
        return member

    def create_plan(self, values: PlanInput) -> MembershipPlan:
        plan = MembershipPlan(**values.model_dump())
        self.db.add(plan)
        self._commit()
        return plan

    def update_plan(self, plan_id: int, values: PlanInput) -> MembershipPlan:
        plan = self.db.get(MembershipPlan, plan_id)
        if not plan:
            raise NotFound("Membership plan not found")
        for key, value in values.model_dump().items():
            setattr(plan, key, value)
        self._commit()
        return plan

    def set_plan_active(self, plan_id: int, active: bool) -> MembershipPlan:
        plan = self.db.get(MembershipPlan, plan_id)
        if not plan:
            raise NotFound("Membership plan not found")
        plan.is_active = active
        self._commit()
        return plan

    def create_subscription(self, values: SubscriptionInput, user_id: int) -> Subscription:
        member = self.repo.member(values.member_id)
        plan = self.db.get(MembershipPlan, values.plan_id)
        if not member or not plan:
            raise NotFound("Member or membership plan not found")
        if member.status != "active":
            raise Conflict("Inactive members cannot receive subscriptions")
        if not plan.is_active:
            raise Conflict("Inactive membership plans cannot be purchased")
        if values.discount_amount > plan.price:
            raise Conflict("Discount cannot exceed the plan price")
        latest = self.repo.latest_subscription(member.id)
        start = values.requested_start_date
        if latest and latest.end_date >= start:
            start = latest.end_date + timedelta(days=1)
        sub = Subscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=start,
            end_date=subscription_end_date(start, plan.duration_months),
            original_price=plan.price,
            discount_amount=values.discount_amount,
            final_price=plan.price - values.discount_amount,
            created_by_user_id=user_id,
        )
        self.db.add(sub)
        self._commit()
        return sub

    def remaining_balance(self, subscription_id: int) -> Decimal:
        sub = self.repo.subscription(subscription_id)
        if not sub:
            raise NotFound("Subscription not found")
        return sub.final_price - self.repo.paid_total(subscription_id)

    def record_payment(self, values: PaymentInput, user_id: int, paid_at: datetime | None = None) -> Payment:
        sub = self.repo.subscription(values.subscription_id)
        if not sub:
            raise NotFound("Subscription not found")
        if sub.member_id != values.member_id:
            raise Conflict("Subscription does not belong to this member")
        remaining = sub.final_price - self.repo.paid_total(sub.id)
        if values.amount > remaining:
            raise Conflict(f"Payment exceeds remaining balance ({remaining:.2f})")
        payment = Payment(
            **values.model_dump(), recorded_by_user_id=user_id, paid_at=paid_at or datetime.now(timezone.utc)
        )
        self.db.add(payment)
        self._commit()
        return payment

    def check_in(self, values: AttendanceInput, user_id: int, now: datetime | None = None) -> Attendance:
        now = now or datetime.now(timezone.utc)
        local_day = now.astimezone(ZoneInfo(settings.gym_timezone)).date()
        member = self.repo.member(values.member_id)
        if not member:
            raise NotFound("Member not found")
        if member.status != "active":
            raise Conflict("Inactive member cannot check in")
        if not self.repo.active_subscription(member.id, local_day):
            raise Conflict("Member does not have an active subscription")
        if self.db.scalar(
            select(Attendance.id).where(Attendance.member_id == member.id, Attendance.attendance_date == local_day)
        ):
            raise Conflict("Member has already checked in today")
        row = Attendance(
            member_id=member.id,
            attendance_date=local_day,
            checked_in_at=now,
            recorded_by_user_id=user_id,
            notes=values.notes,
        )
        self.db.add(row)
        self._commit()
        return row

    def create_trainer(self, values: TrainerInput) -> Trainer:
        trainer = Trainer(**values.model_dump())
        self.db.add(trainer)
        self._commit()
        return trainer

    def update_trainer(self, trainer_id: int, values: TrainerInput) -> Trainer:
        trainer = self.db.get(Trainer, trainer_id)
        if not trainer:
            raise NotFound("Trainer not found")
        for key, value in values.model_dump().items():
            setattr(trainer, key, value)
        self._commit()
        return trainer

    def set_trainer_active(self, trainer_id: int, active: bool) -> Trainer:
        trainer = self.db.get(Trainer, trainer_id)
        if not trainer:
            raise NotFound("Trainer not found")
        trainer.status = "active" if active else "inactive"
        self._commit()
        return trainer

    def assign_trainer(self, values: AssignmentInput) -> TrainerAssignment:
        trainer, member = self.db.get(Trainer, values.trainer_id), self.repo.member(values.member_id)
        if not trainer or not member:
            raise NotFound("Trainer or member not found")
        if trainer.status != "active" or member.status != "active":
            raise Conflict("Trainer and member must both be active")
        current = self.repo.active_assignment(member.id)
        if current:
            current.is_active = False
            current.end_date = values.start_date - timedelta(days=1)
        row = TrainerAssignment(**values.model_dump())
        self.db.add(row)
        self._commit()
        return row

    def create_exercise(self, values: ExerciseInput) -> Exercise:
        row = Exercise(**values.model_dump())
        self.db.add(row)
        self._commit()
        return row

    def create_workout(self, values: WorkoutInput) -> WorkoutPlan:
        if values.end_date and values.end_date < values.start_date:
            raise Conflict("Workout end date cannot precede its start date")
        if not self.repo.member(values.member_id) or not self.db.get(Trainer, values.trainer_id):
            raise NotFound("Member or trainer not found")
        row = WorkoutPlan(**values.model_dump())
        self.db.add(row)
        self._commit()
        return row

    def update_workout(self, workout_id: int, values: WorkoutInput) -> WorkoutPlan:
        row = self.db.get(WorkoutPlan, workout_id)
        if not row:
            raise NotFound("Workout plan not found")
        if values.end_date and values.end_date < values.start_date:
            raise Conflict("Workout end date cannot precede its start date")
        for key, value in values.model_dump().items():
            setattr(row, key, value)
        self._commit()
        return row

    def add_workout_exercise(self, workout_id: int, values: WorkoutExerciseInput) -> WorkoutExercise:
        if not self.db.get(WorkoutPlan, workout_id) or not self.db.get(Exercise, values.exercise_id):
            raise NotFound("Workout plan or exercise not found")
        row = WorkoutExercise(workout_plan_id=workout_id, **values.model_dump())
        self.db.add(row)
        self._commit()
        return row
