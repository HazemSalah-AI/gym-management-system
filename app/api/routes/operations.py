from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import require_permission
from app.core.csrf import validate_csrf_token
from app.db.session import get_db
from app.models import Exercise, Member, MembershipPlan, Subscription, Trainer, WorkoutPlan
from app.repositories.domain import DomainRepository
from app.schemas.domain import (
    AssignmentInput,
    AttendanceInput,
    ExerciseInput,
    MemberInput,
    PaymentInput,
    PlanInput,
    StaffUserInput,
    SubscriptionInput,
    TrainerInput,
    WorkoutExerciseInput,
    WorkoutInput,
)
from app.services.domain import Conflict, DomainService, NotFound
from app.services.users import UserAdminService

router = APIRouter(prefix="/api", tags=["Gym operations"])
csrf = Depends(validate_csrf_token)


def current(permission: str):
    return Depends(require_permission(permission))


def service_error(exc: Exception):
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, NotFound) else status.HTTP_409_CONFLICT
    raise HTTPException(code, str(exc)) from exc


def member_json(row: Member):
    return {
        "id": row.id,
        "member_number": row.member_number,
        "full_name": row.full_name,
        "phone": row.phone,
        "email": row.email,
        "gender": row.gender,
        "date_of_birth": row.date_of_birth,
        "address": row.address,
        "registration_date": row.registration_date,
        "status": row.status,
        "emergency_contact_name": row.emergency_contact_name,
        "emergency_contact_phone": row.emergency_contact_phone,
        "notes": row.notes,
    }


@router.get("/members")
def members(
    search: str = "",
    member_status: str = Query("", alias="status"),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    user=current("members.read"),
):
    rows, total = DomainRepository(db).members(search, member_status, page)
    return {"items": [member_json(row) for row in rows], "total": total, "page": page, "per_page": 20}


@router.post("/members", status_code=201, dependencies=[csrf])
def create_member(values: MemberInput, db: Session = Depends(get_db), user=current("members.write")):
    try:
        return member_json(DomainService(db).create_member(values))
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.get("/members/{member_id}")
def member_detail(member_id: int, db: Session = Depends(get_db), user=current("members.read")):
    row = db.get(Member, member_id)
    if not row:
        raise HTTPException(404, "Member not found")
    data = member_json(row)
    data["subscriptions"] = [
        {
            "id": s.id,
            "plan": s.plan.name,
            "start_date": s.start_date,
            "end_date": s.end_date,
            "final_price": s.final_price,
            "paid_amount": sum((p.amount for p in s.payments), start=0),
        }
        for s in db.scalars(
            select(Subscription)
            .options(selectinload(Subscription.plan), selectinload(Subscription.payments))
            .where(Subscription.member_id == member_id)
            .order_by(Subscription.id.desc())
        )
    ]
    return data


@router.put("/members/{member_id}", dependencies=[csrf])
def update_member(member_id: int, values: MemberInput, db: Session = Depends(get_db), user=current("members.write")):
    try:
        return member_json(DomainService(db).update_member(member_id, values))
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.post("/members/{member_id}/status", dependencies=[csrf])
def member_status(member_id: int, active: bool, db: Session = Depends(get_db), user=current("members.deactivate")):
    try:
        return member_json(DomainService(db).set_member_active(member_id, active))
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.get("/membership-plans")
def plans(db: Session = Depends(get_db), user=current("memberships.read")):
    return list(db.scalars(select(MembershipPlan).order_by(MembershipPlan.name)))


@router.post("/membership-plans", status_code=201, dependencies=[csrf])
def create_plan(values: PlanInput, db: Session = Depends(get_db), user=current("memberships.write")):
    try:
        row = DomainService(db).create_plan(values)
        return {
            "id": row.id,
            "name": row.name,
            "duration_months": row.duration_months,
            "price": row.price,
            "description": row.description,
            "is_active": row.is_active,
        }
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.put("/membership-plans/{plan_id}", dependencies=[csrf])
def update_plan(plan_id: int, values: PlanInput, db: Session = Depends(get_db), user=current("memberships.write")):
    try:
        row = DomainService(db).update_plan(plan_id, values)
        return {"id": row.id, "name": row.name, "duration_months": row.duration_months, "price": row.price}
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.post("/membership-plans/{plan_id}/status", dependencies=[csrf])
def plan_status(plan_id: int, active: bool, db: Session = Depends(get_db), user=current("memberships.write")):
    try:
        row = DomainService(db).set_plan_active(plan_id, active)
        return {"id": row.id, "is_active": row.is_active}
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.post("/subscriptions", status_code=201, dependencies=[csrf])
def create_subscription(values: SubscriptionInput, db: Session = Depends(get_db), user=current("subscriptions.write")):
    try:
        row = DomainService(db).create_subscription(values, user.id)
        return {
            "id": row.id,
            "member_id": row.member_id,
            "plan_id": row.plan_id,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "original_price": row.original_price,
            "discount_amount": row.discount_amount,
            "final_price": row.final_price,
            "remaining_balance": row.final_price,
        }
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.get("/subscriptions/{subscription_id}")
def subscription_detail(subscription_id: int, db: Session = Depends(get_db), user=current("subscriptions.read")):
    row = DomainRepository(db).subscription(subscription_id)
    if not row:
        raise HTTPException(404, "Subscription not found")
    paid = sum((p.amount for p in row.payments), start=0)
    return {
        "id": row.id,
        "member_id": row.member_id,
        "plan_id": row.plan_id,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "status": row.status,
        "original_price": row.original_price,
        "discount_amount": row.discount_amount,
        "final_price": row.final_price,
        "paid_amount": paid,
        "remaining_balance": row.final_price - paid,
    }


@router.get("/payments")
def payments(
    page: int = Query(1, ge=1),
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    user=current("payments.read"),
):
    rows, total = DomainRepository(db).payments(page, 20, start, end)
    return {
        "items": [
            {
                "id": p.id,
                "member_id": p.member_id,
                "member_name": p.member.full_name,
                "subscription_id": p.subscription_id,
                "amount": p.amount,
                "method": p.method,
                "paid_at": p.paid_at,
                "reference_number": p.reference_number,
            }
            for p in rows
        ],
        "total": total,
        "page": page,
        "per_page": 20,
    }


@router.post("/payments", status_code=201, dependencies=[csrf])
def record_payment(values: PaymentInput, db: Session = Depends(get_db), user=current("payments.write")):
    try:
        row = DomainService(db).record_payment(values, user.id)
        return {
            "id": row.id,
            "amount": row.amount,
            "subscription_id": row.subscription_id,
            "remaining_balance": DomainService(db).remaining_balance(row.subscription_id),
        }
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.get("/payments/{payment_id}")
def payment_detail(payment_id: int, db: Session = Depends(get_db), user=current("payments.read")):
    from app.models import Payment

    row = db.scalar(
        select(Payment)
        .options(selectinload(Payment.member), selectinload(Payment.subscription))
        .where(Payment.id == payment_id)
    )
    if not row:
        raise HTTPException(404, "Payment not found")
    return {
        "id": row.id,
        "member_id": row.member_id,
        "member_name": row.member.full_name,
        "subscription_id": row.subscription_id,
        "amount": row.amount,
        "method": row.method,
        "paid_at": row.paid_at,
        "reference_number": row.reference_number,
        "notes": row.notes,
        "recorded_by_user_id": row.recorded_by_user_id,
    }


@router.get("/attendance")
def attendance(
    day: date | None = None,
    search: str = "",
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    user=current("attendance.read"),
):
    rows, total = DomainRepository(db).attendance(day, search, page)
    return {
        "items": [
            {
                "id": a.id,
                "member_id": a.member_id,
                "member_name": a.member.full_name,
                "attendance_date": a.attendance_date,
                "checked_in_at": a.checked_in_at,
            }
            for a in rows
        ],
        "total": total,
        "page": page,
        "per_page": 20,
    }


@router.post("/attendance", status_code=201, dependencies=[csrf])
def check_in(values: AttendanceInput, db: Session = Depends(get_db), user=current("attendance.record")):
    try:
        row = DomainService(db).check_in(values, user.id)
        return {
            "id": row.id,
            "member_id": row.member_id,
            "attendance_date": row.attendance_date,
            "checked_in_at": row.checked_in_at,
        }
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.get("/trainers")
def trainers(
    search: str = "",
    trainer_status: str = Query("", alias="status"),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    user=current("trainers.read"),
):
    rows, total = DomainRepository(db).trainers(search, trainer_status, page)
    return {
        "items": [
            {
                "id": t.id,
                "full_name": t.full_name,
                "phone": t.phone,
                "email": t.email,
                "specialization": t.specialization,
                "status": t.status,
            }
            for t in rows
        ],
        "total": total,
        "page": page,
        "per_page": 20,
    }


@router.post("/trainers", status_code=201, dependencies=[csrf])
def create_trainer(values: TrainerInput, db: Session = Depends(get_db), user=current("trainers.write")):
    try:
        row = DomainService(db).create_trainer(values)
        return {
            "id": row.id,
            "full_name": row.full_name,
            "phone": row.phone,
            "email": row.email,
            "specialization": row.specialization,
            "status": row.status,
        }
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.get("/trainers/{trainer_id}")
def trainer_detail(trainer_id: int, db: Session = Depends(get_db), user=current("trainers.read")):
    from app.models import TrainerAssignment

    row = db.get(Trainer, trainer_id)
    if not row:
        raise HTTPException(404, "Trainer not found")
    assignments = db.scalars(
        select(TrainerAssignment)
        .options(selectinload(TrainerAssignment.member))
        .where(TrainerAssignment.trainer_id == trainer_id)
        .order_by(TrainerAssignment.id.desc())
    )
    return {
        "id": row.id,
        "full_name": row.full_name,
        "phone": row.phone,
        "email": row.email,
        "specialization": row.specialization,
        "notes": row.notes,
        "status": row.status,
        "assignments": [
            {
                "member_id": a.member_id,
                "member_name": a.member.full_name,
                "start_date": a.start_date,
                "end_date": a.end_date,
                "is_active": a.is_active,
            }
            for a in assignments
        ],
    }


@router.put("/trainers/{trainer_id}", dependencies=[csrf])
def update_trainer(
    trainer_id: int, values: TrainerInput, db: Session = Depends(get_db), user=current("trainers.write")
):
    try:
        row = DomainService(db).update_trainer(trainer_id, values)
        return {
            "id": row.id,
            "full_name": row.full_name,
            "phone": row.phone,
            "email": row.email,
            "specialization": row.specialization,
            "status": row.status,
        }
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.post("/trainers/{trainer_id}/status", dependencies=[csrf])
def trainer_status(trainer_id: int, active: bool, db: Session = Depends(get_db), user=current("trainers.write")):
    try:
        row = DomainService(db).set_trainer_active(trainer_id, active)
        return {"id": row.id, "status": row.status}
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.post("/trainer-assignments", status_code=201, dependencies=[csrf])
def assign_trainer(values: AssignmentInput, db: Session = Depends(get_db), user=current("trainers.write")):
    try:
        row = DomainService(db).assign_trainer(values)
        return {
            "id": row.id,
            "trainer_id": row.trainer_id,
            "member_id": row.member_id,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "is_active": row.is_active,
        }
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.get("/exercises")
def exercises(db: Session = Depends(get_db), user=current("workouts.read")):
    return list(db.scalars(select(Exercise).order_by(Exercise.name)))


@router.post("/exercises", status_code=201, dependencies=[csrf])
def create_exercise(values: ExerciseInput, db: Session = Depends(get_db), user=current("workouts.write")):
    try:
        row = DomainService(db).create_exercise(values)
        return {
            "id": row.id,
            "name": row.name,
            "muscle_group": row.muscle_group,
            "description": row.description,
            "is_active": row.is_active,
        }
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.get("/workouts")
def workouts(db: Session = Depends(get_db), user=current("workouts.read")):
    rows = db.scalars(
        select(WorkoutPlan)
        .options(selectinload(WorkoutPlan.member), selectinload(WorkoutPlan.trainer))
        .order_by(WorkoutPlan.id.desc())
        .limit(100)
    )
    return [
        {
            "id": w.id,
            "name": w.name,
            "member_name": w.member.full_name,
            "trainer_name": w.trainer.full_name,
            "start_date": w.start_date,
            "end_date": w.end_date,
            "status": w.status,
        }
        for w in rows
    ]


@router.get("/workouts/{workout_id}")
def workout_detail(workout_id: int, db: Session = Depends(get_db), user=current("workouts.read")):
    row = DomainRepository(db).workout(workout_id)
    if not row:
        raise HTTPException(404, "Workout plan not found")
    return {
        "id": row.id,
        "name": row.name,
        "member_id": row.member_id,
        "member_name": row.member.full_name,
        "trainer_id": row.trainer_id,
        "trainer_name": row.trainer.full_name,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "notes": row.notes,
        "status": row.status,
        "exercises": [
            {
                "id": item.id,
                "exercise_id": item.exercise_id,
                "name": item.exercise.name,
                "position": item.position,
                "sets": item.sets,
                "reps": item.reps,
                "weight": item.weight,
                "rest_seconds": item.rest_seconds,
                "notes": item.notes,
            }
            for item in row.exercises
        ],
    }


@router.post("/workouts", status_code=201, dependencies=[csrf])
def create_workout(values: WorkoutInput, db: Session = Depends(get_db), user=current("workouts.write")):
    try:
        row = DomainService(db).create_workout(values)
        return {
            "id": row.id,
            "name": row.name,
            "member_id": row.member_id,
            "trainer_id": row.trainer_id,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "status": row.status,
        }
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.post("/workouts/{workout_id}/exercises", status_code=201, dependencies=[csrf])
def add_exercise(
    workout_id: int, values: WorkoutExerciseInput, db: Session = Depends(get_db), user=current("workouts.write")
):
    try:
        row = DomainService(db).add_workout_exercise(workout_id, values)
        return {
            "id": row.id,
            "workout_plan_id": row.workout_plan_id,
            "exercise_id": row.exercise_id,
            "position": row.position,
            "sets": row.sets,
            "reps": row.reps,
            "weight": row.weight,
            "rest_seconds": row.rest_seconds,
        }
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.post("/users", status_code=201, dependencies=[csrf])
def create_user(values: StaffUserInput, db: Session = Depends(get_db), user=current("users.manage")):
    try:
        row = UserAdminService(db).create(values)
        return {
            "id": row.id,
            "username": row.username,
            "email": row.email,
            "role": row.role.name,
            "is_active": row.is_active,
        }
    except (Conflict, NotFound) as exc:
        service_error(exc)


@router.post("/users/{user_id}/status", dependencies=[csrf])
def user_status(user_id: int, active: bool, db: Session = Depends(get_db), user=current("users.manage")):
    try:
        row = UserAdminService(db).set_active(user_id, active, user.id)
        return {"id": row.id, "is_active": row.is_active}
    except (Conflict, NotFound) as exc:
        service_error(exc)
