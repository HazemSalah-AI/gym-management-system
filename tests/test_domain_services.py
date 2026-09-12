from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import Attendance, Payment, TrainerAssignment, WorkoutExercise
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
from app.services.domain import Conflict, DomainService, subscription_end_date


def create_member_plan(db):
    service = DomainService(db)
    member = service.create_member(MemberInput(full_name="Hazem Salah", phone="01012345678"))
    plan = service.create_plan(PlanInput(name="Monthly", duration_months=1, price=Decimal("500.00")))
    return service, member, plan


@pytest.mark.parametrize(
    "start,months,expected",
    [
        (date(2026, 1, 31), 1, date(2026, 2, 27)),
        (date(2024, 2, 29), 12, date(2025, 2, 27)),
        (date(2026, 9, 12), 3, date(2026, 12, 11)),
    ],
)
def test_calendar_month_subscription_dates(start, months, expected):
    assert subscription_end_date(start, months) == expected


def test_member_number_and_deactivation(db):
    service, member, _ = create_member_plan(db)
    assert member.member_number == f"GYM-{member.id:06d}"
    service.set_member_active(member.id, False)
    assert member.status == "inactive"


def test_subscription_snapshot_discount_and_early_renewal(db, users):
    service, member, plan = create_member_plan(db)
    first = service.create_subscription(
        SubscriptionInput(
            member_id=member.id, plan_id=plan.id, requested_start_date=date(2026, 9, 1), discount_amount=Decimal("50")
        ),
        users["Admin"],
    )
    plan.price = Decimal("700")
    db.commit()
    renewal = service.create_subscription(
        SubscriptionInput(member_id=member.id, plan_id=plan.id, requested_start_date=date(2026, 9, 15)), users["Admin"]
    )
    assert first.original_price == Decimal("500") and first.final_price == Decimal("450")
    assert renewal.start_date == first.end_date.replace(day=first.end_date.day) + (renewal.start_date - first.end_date)
    assert renewal.start_date == date(2026, 10, 1)
    assert renewal.original_price == Decimal("700")


def test_expired_subscription_uses_requested_date(db, users):
    service, member, plan = create_member_plan(db)
    service.create_subscription(
        SubscriptionInput(member_id=member.id, plan_id=plan.id, requested_start_date=date(2025, 1, 1)), users["Admin"]
    )
    renewal = service.create_subscription(
        SubscriptionInput(member_id=member.id, plan_id=plan.id, requested_start_date=date(2026, 9, 12)), users["Admin"]
    )
    assert renewal.start_date == date(2026, 9, 12)


def test_inactive_plan_and_invalid_discount_rejected(db, users):
    service, member, plan = create_member_plan(db)
    service.set_plan_active(plan.id, False)
    with pytest.raises(Conflict):
        service.create_subscription(SubscriptionInput(member_id=member.id, plan_id=plan.id), users["Admin"])
    service.set_plan_active(plan.id, True)
    with pytest.raises(Conflict):
        service.create_subscription(
            SubscriptionInput(member_id=member.id, plan_id=plan.id, discount_amount=Decimal("501")), users["Admin"]
        )


def test_partial_full_and_overpayment(db, users):
    service, member, plan = create_member_plan(db)
    sub = service.create_subscription(
        SubscriptionInput(member_id=member.id, plan_id=plan.id, requested_start_date=date(2026, 9, 1)), users["Admin"]
    )
    service.record_payment(
        PaymentInput(member_id=member.id, subscription_id=sub.id, amount=Decimal("200"), method="cash"), users["Admin"]
    )
    assert service.remaining_balance(sub.id) == Decimal("300")
    service.record_payment(
        PaymentInput(
            member_id=member.id, subscription_id=sub.id, amount=Decimal("300"), method="card", reference_number="CARD-1"
        ),
        users["Admin"],
    )
    assert service.remaining_balance(sub.id) == 0
    with pytest.raises(Conflict):
        service.record_payment(
            PaymentInput(member_id=member.id, subscription_id=sub.id, amount=Decimal("1"), method="cash"),
            users["Admin"],
        )
    assert db.scalar(select(func.count()).select_from(Payment)) == 2


def test_wrong_member_payment_rejected(db, users):
    service, member, plan = create_member_plan(db)
    other = service.create_member(MemberInput(full_name="Other Member", phone="01098765432"))
    sub = service.create_subscription(SubscriptionInput(member_id=member.id, plan_id=plan.id), users["Admin"])
    with pytest.raises(Conflict):
        service.record_payment(
            PaymentInput(member_id=other.id, subscription_id=sub.id, amount=Decimal("10"), method="cash"),
            users["Admin"],
        )


def test_attendance_eligibility_duplicate_and_next_day(db, users):
    service, member, plan = create_member_plan(db)
    service.create_subscription(
        SubscriptionInput(member_id=member.id, plan_id=plan.id, requested_start_date=date(2026, 9, 1)), users["Admin"]
    )
    first = datetime(2026, 9, 12, 8, tzinfo=timezone.utc)
    service.check_in(AttendanceInput(member_id=member.id), users["Admin"], first)
    with pytest.raises(Conflict):
        service.check_in(AttendanceInput(member_id=member.id), users["Admin"], first)
    service.check_in(
        AttendanceInput(member_id=member.id), users["Admin"], datetime(2026, 9, 13, 8, tzinfo=timezone.utc)
    )
    assert db.scalar(select(func.count()).select_from(Attendance)) == 2


def test_expired_and_inactive_attendance_rejected(db, users):
    service, member, plan = create_member_plan(db)
    service.create_subscription(
        SubscriptionInput(member_id=member.id, plan_id=plan.id, requested_start_date=date(2025, 1, 1)), users["Admin"]
    )
    with pytest.raises(Conflict):
        service.check_in(
            AttendanceInput(member_id=member.id), users["Admin"], datetime(2026, 9, 12, tzinfo=timezone.utc)
        )
    service.set_member_active(member.id, False)
    with pytest.raises(Conflict):
        service.check_in(
            AttendanceInput(member_id=member.id), users["Admin"], datetime(2025, 1, 2, tzinfo=timezone.utc)
        )


def test_trainer_assignment_history_and_workout_exercise(db):
    service, member, _ = create_member_plan(db)
    first = service.create_trainer(TrainerInput(full_name="Trainer One", phone="01011111111"))
    second = service.create_trainer(TrainerInput(full_name="Trainer Two", phone="01022222222"))
    service.assign_trainer(AssignmentInput(trainer_id=first.id, member_id=member.id, start_date=date(2026, 9, 1)))
    active = service.assign_trainer(
        AssignmentInput(trainer_id=second.id, member_id=member.id, start_date=date(2026, 9, 10))
    )
    assignments = list(db.scalars(select(TrainerAssignment).order_by(TrainerAssignment.id)))
    assert not assignments[0].is_active and assignments[0].end_date == date(2026, 9, 9)
    assert active.is_active
    exercise = service.create_exercise(ExerciseInput(name="Bench press", muscle_group="Chest"))
    workout = service.create_workout(
        WorkoutInput(name="Push day", member_id=member.id, trainer_id=second.id, start_date=date(2026, 9, 10))
    )
    service.add_workout_exercise(
        workout.id,
        WorkoutExerciseInput(
            exercise_id=exercise.id, position=1, sets=4, reps=10, weight=Decimal("40"), rest_seconds=90
        ),
    )
    item = db.scalar(select(WorkoutExercise))
    assert item.position == 1 and item.weight == Decimal("40")
