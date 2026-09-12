from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Attendance,
    Member,
    Payment,
    Subscription,
    Trainer,
    TrainerAssignment,
    WorkoutExercise,
    WorkoutPlan,
)


class DomainRepository:
    def __init__(self, db: Session):
        self.db = db

    def member(self, member_id: int) -> Member | None:
        return self.db.get(Member, member_id)

    def members(self, search: str = "", status: str = "", page: int = 1, per_page: int = 20):
        query = select(Member)
        count = select(func.count()).select_from(Member)
        filters = []
        if search:
            term = f"%{search.strip()}%"
            filters.append(
                or_(Member.full_name.ilike(term), Member.phone.ilike(term), Member.member_number.ilike(term))
            )
        if status in {"active", "inactive"}:
            filters.append(Member.status == status)
        query = query.where(*filters)
        count = count.where(*filters)
        total = self.db.scalar(count) or 0
        rows = list(self.db.scalars(query.order_by(Member.id.desc()).offset((page - 1) * per_page).limit(per_page)))
        return rows, total

    def active_subscription(self, member_id: int, on_date: date) -> Subscription | None:
        return self.db.scalar(
            select(Subscription)
            .where(
                Subscription.member_id == member_id,
                Subscription.status == "active",
                Subscription.start_date <= on_date,
                Subscription.end_date >= on_date,
            )
            .order_by(Subscription.end_date.desc())
            .limit(1)
        )

    def latest_subscription(self, member_id: int) -> Subscription | None:
        return self.db.scalar(
            select(Subscription)
            .where(
                Subscription.member_id == member_id,
                Subscription.status == "active",
            )
            .order_by(Subscription.end_date.desc())
            .limit(1)
        )

    def subscription(self, subscription_id: int) -> Subscription | None:
        return self.db.scalar(
            select(Subscription)
            .options(
                selectinload(Subscription.member), selectinload(Subscription.plan), selectinload(Subscription.payments)
            )
            .where(Subscription.id == subscription_id)
        )

    def paid_total(self, subscription_id: int) -> Decimal:
        return self.db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.subscription_id == subscription_id)
        ) or Decimal("0")

    def payments(self, page: int = 1, per_page: int = 20, start: date | None = None, end: date | None = None):
        filters = []
        if start:
            filters.append(func.date(Payment.paid_at) >= start)
        if end:
            filters.append(func.date(Payment.paid_at) <= end)
        query = (
            select(Payment).options(selectinload(Payment.member), selectinload(Payment.subscription)).where(*filters)
        )
        total = self.db.scalar(select(func.count()).select_from(Payment).where(*filters)) or 0
        return list(
            self.db.scalars(query.order_by(Payment.paid_at.desc()).offset((page - 1) * per_page).limit(per_page))
        ), total

    def attendance(self, day: date | None = None, search: str = "", page: int = 1, per_page: int = 20):
        query = select(Attendance).join(Attendance.member).options(selectinload(Attendance.member))
        filters = []
        if day:
            filters.append(Attendance.attendance_date == day)
        if search:
            term = f"%{search.strip()}%"
            filters.append(or_(Member.full_name.ilike(term), Member.member_number.ilike(term)))
        query = query.where(*filters)
        total = (
            self.db.scalar(select(func.count()).select_from(Attendance).join(Attendance.member).where(*filters)) or 0
        )
        return list(
            self.db.scalars(
                query.order_by(Attendance.checked_in_at.desc()).offset((page - 1) * per_page).limit(per_page)
            )
        ), total

    def trainers(self, search: str = "", status: str = "", page: int = 1, per_page: int = 20):
        filters = []
        if search:
            term = f"%{search.strip()}%"
            filters.append(
                or_(Trainer.full_name.ilike(term), Trainer.phone.ilike(term), Trainer.specialization.ilike(term))
            )
        if status in {"active", "inactive"}:
            filters.append(Trainer.status == status)
        total = self.db.scalar(select(func.count()).select_from(Trainer).where(*filters)) or 0
        rows = list(
            self.db.scalars(
                select(Trainer)
                .where(*filters)
                .order_by(Trainer.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
        )
        return rows, total

    def active_assignment(self, member_id: int) -> TrainerAssignment | None:
        return self.db.scalar(
            select(TrainerAssignment).where(
                TrainerAssignment.member_id == member_id, TrainerAssignment.is_active.is_(True)
            )
        )

    def workout(self, workout_id: int) -> WorkoutPlan | None:
        return self.db.scalar(
            select(WorkoutPlan)
            .options(
                selectinload(WorkoutPlan.member),
                selectinload(WorkoutPlan.trainer),
                selectinload(WorkoutPlan.exercises).selectinload(WorkoutExercise.exercise),
            )
            .where(WorkoutPlan.id == workout_id)
        )
