import csv
import io
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import get_current_user, require_permission
from app.core.csrf import get_csrf_token, validate_csrf_value
from app.db.session import get_db
from app.models import Exercise, Member, MembershipPlan, Subscription, Trainer, User, WorkoutPlan
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
from app.services.auth import AuthService, InvalidCredentials
from app.services.domain import Conflict, DomainService, NotFound
from app.services.reporting import ReportingService
from app.services.users import UserAdminService

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="app/templates")


def has_permission(user: User, code: str) -> bool:
    return any(p.code == code for p in user.role.permissions)


def context(request: Request, user: User | None = None, **values):
    return {
        "request": request,
        "user": user,
        "csrf_token": get_csrf_token(request),
        "has_permission": has_permission,
        **values,
    }


def form_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(e["msg"] for e in exc.errors())
    return str(exc)


@router.get("/")
def root(request: Request):
    return RedirectResponse("/dashboard" if request.session.get("user_id") else "/login", 303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", context(request))


@router.post("/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    validate_csrf_value(request, csrf_token)
    previous = request.session.get("session_token")
    try:
        user, token = AuthService(db).login(username, password, previous if isinstance(previous, str) else None)
    except InvalidCredentials:
        return templates.TemplateResponse(
            request, "login.html", context(request, error="Invalid username or password"), status_code=401
        )
    request.session.clear()
    request.session.update(user_id=user.id, session_token=token)
    get_csrf_token(request)
    return RedirectResponse("/dashboard", 303)


@router.post("/logout")
def logout_form(
    request: Request, csrf_token: str = Form(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    validate_csrf_value(request, csrf_token)
    AuthService(db).logout(request.session.get("session_token"))
    request.session.clear()
    return RedirectResponse("/login", 303)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("dashboard.read"))
):
    metrics, recent_payments, expirations, recent_members = ReportingService(db).dashboard()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        context(
            request,
            user,
            title="Dashboard",
            metrics=metrics,
            recent_payments=recent_payments,
            expirations=expirations,
            recent_members=recent_members,
        ),
    )


@router.get("/members", response_class=HTMLResponse)
def member_list(
    request: Request,
    search: str = "",
    status: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("members.read")),
):
    rows, total = DomainRepository(db).members(search, status, max(page, 1))
    return templates.TemplateResponse(
        request,
        "members.html",
        context(
            request,
            user,
            title="Members",
            members=rows,
            total=total,
            page=max(page, 1),
            pages=max(1, (total + 19) // 20),
            search=search,
            status=status,
        ),
    )


@router.get("/members/new", response_class=HTMLResponse)
def member_new(request: Request, user: User = Depends(require_permission("members.write"))):
    return templates.TemplateResponse(
        request, "member_form.html", context(request, user, title="New member", member=None)
    )


@router.post("/members/new", response_class=HTMLResponse)
async def member_create(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("members.write"))
):
    data = dict(await request.form())
    validate_csrf_value(request, data.pop("csrf_token", None))
    data["email"] = data.get("email") or None
    data["date_of_birth"] = data.get("date_of_birth") or None
    data["gender"] = data.get("gender") or None
    try:
        row = DomainService(db).create_member(MemberInput(**data))
        return RedirectResponse(f"/members/{row.id}?message=Member+created", 303)
    except (ValidationError, Conflict, NotFound) as exc:
        return templates.TemplateResponse(
            request,
            "member_form.html",
            context(request, user, title="New member", member=data, error=form_error(exc)),
            status_code=422,
        )


@router.get("/members/{member_id}", response_class=HTMLResponse)
def member_view(
    member_id: int,
    request: Request,
    message: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("members.read")),
):
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(404, "Member not found")
    subs = list(
        db.scalars(
            select(Subscription)
            .options(selectinload(Subscription.plan), selectinload(Subscription.payments))
            .where(Subscription.member_id == member_id)
            .order_by(Subscription.id.desc())
        )
    )
    assignments = member.trainer_assignments
    return templates.TemplateResponse(
        request,
        "member_detail.html",
        context(
            request,
            user,
            title=member.full_name,
            member=member,
            subscriptions=subs,
            assignments=assignments,
            message=message,
        ),
    )


@router.get("/members/{member_id}/edit", response_class=HTMLResponse)
def member_edit(
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("members.write")),
):
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(404, "Member not found")
    return templates.TemplateResponse(
        request, "member_form.html", context(request, user, title="Edit member", member=member)
    )


@router.post("/members/{member_id}/edit", response_class=HTMLResponse)
async def member_update(
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("members.write")),
):
    data = dict(await request.form())
    validate_csrf_value(request, data.pop("csrf_token", None))
    data["email"], data["date_of_birth"], data["gender"] = (
        data.get("email") or None,
        data.get("date_of_birth") or None,
        data.get("gender") or None,
    )
    try:
        DomainService(db).update_member(member_id, MemberInput(**data))
        return RedirectResponse(f"/members/{member_id}?message=Member+updated", 303)
    except (ValidationError, Conflict, NotFound) as exc:
        return templates.TemplateResponse(
            request,
            "member_form.html",
            context(request, user, title="Edit member", member=data, error=form_error(exc)),
            status_code=422,
        )


@router.post("/members/{member_id}/status")
def member_toggle(
    member_id: int,
    request: Request,
    active: bool = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("members.deactivate")),
):
    validate_csrf_value(request, csrf_token)
    try:
        DomainService(db).set_member_active(member_id, active)
    except (Conflict, NotFound) as exc:
        raise HTTPException(409, str(exc)) from exc
    return RedirectResponse(f"/members/{member_id}?message=Status+updated", 303)


@router.get("/memberships", response_class=HTMLResponse)
def memberships(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("memberships.read"))
):
    plans = list(db.scalars(select(MembershipPlan).order_by(MembershipPlan.name)))
    subs = list(
        db.scalars(
            select(Subscription)
            .options(selectinload(Subscription.member), selectinload(Subscription.plan))
            .order_by(Subscription.id.desc())
            .limit(50)
        )
    )
    return templates.TemplateResponse(
        request, "memberships.html", context(request, user, title="Memberships", plans=plans, subscriptions=subs)
    )


@router.post("/membership-plans")
def plan_create(
    request: Request,
    csrf_token: str = Form(...),
    name: str = Form(...),
    duration_months: int = Form(...),
    price: Decimal = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("memberships.write")),
):
    validate_csrf_value(request, csrf_token)
    try:
        DomainService(db).create_plan(
            PlanInput(name=name, duration_months=duration_months, price=price, description=description or None)
        )
    except (ValidationError, Conflict, NotFound) as exc:
        raise HTTPException(409, form_error(exc)) from exc
    return RedirectResponse("/memberships", 303)


@router.post("/subscriptions")
def subscription_create(
    request: Request,
    csrf_token: str = Form(...),
    member_id: int = Form(...),
    plan_id: int = Form(...),
    requested_start_date: date = Form(...),
    discount_amount: Decimal = Form(0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("subscriptions.write")),
):
    validate_csrf_value(request, csrf_token)
    try:
        DomainService(db).create_subscription(
            SubscriptionInput(
                member_id=member_id,
                plan_id=plan_id,
                requested_start_date=requested_start_date,
                discount_amount=discount_amount,
            ),
            user.id,
        )
    except (ValidationError, Conflict, NotFound) as exc:
        raise HTTPException(409, form_error(exc)) from exc
    return RedirectResponse("/memberships", 303)


@router.get("/payments", response_class=HTMLResponse)
def payments(
    request: Request,
    start: date | None = None,
    end: date | None = None,
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("payments.read")),
):
    rows, total = DomainRepository(db).payments(max(page, 1), 20, start, end)
    subscriptions = list(
        db.scalars(
            select(Subscription).options(selectinload(Subscription.member)).order_by(Subscription.id.desc()).limit(100)
        )
    )
    return templates.TemplateResponse(
        request,
        "payments.html",
        context(
            request,
            user,
            title="Payments",
            payments=rows,
            subscriptions=subscriptions,
            total=total,
            page=page,
            pages=max(1, (total + 19) // 20),
            start=start,
            end=end,
        ),
    )


@router.post("/payments")
def payment_create(
    request: Request,
    csrf_token: str = Form(...),
    subscription_id: int = Form(...),
    amount: Decimal = Form(...),
    method: str = Form(...),
    reference_number: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("payments.write")),
):
    validate_csrf_value(request, csrf_token)
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(404, "Subscription not found")
    try:
        DomainService(db).record_payment(
            PaymentInput(
                member_id=sub.member_id,
                subscription_id=sub.id,
                amount=amount,
                method=method,
                reference_number=reference_number or None,
                notes=notes or None,
            ),
            user.id,
        )
    except (ValidationError, Conflict, NotFound) as exc:
        raise HTTPException(409, form_error(exc)) from exc
    return RedirectResponse("/payments", 303)


@router.get("/attendance", response_class=HTMLResponse)
def attendance(
    request: Request,
    day: date | None = None,
    search: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("attendance.read")),
):
    rows, total = DomainRepository(db).attendance(day or date.today(), search, max(page, 1))
    members = list(db.scalars(select(Member).where(Member.status == "active").order_by(Member.full_name)))
    return templates.TemplateResponse(
        request,
        "attendance.html",
        context(
            request,
            user,
            title="Attendance",
            attendance=rows,
            members=members,
            total=total,
            day=day or date.today(),
            search=search,
        ),
    )


@router.post("/attendance")
def attendance_create(
    request: Request,
    csrf_token: str = Form(...),
    member_id: int = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("attendance.record")),
):
    validate_csrf_value(request, csrf_token)
    try:
        DomainService(db).check_in(AttendanceInput(member_id=member_id, notes=notes or None), user.id)
    except (ValidationError, Conflict, NotFound) as exc:
        raise HTTPException(409, form_error(exc)) from exc
    return RedirectResponse("/attendance", 303)


@router.get("/trainers", response_class=HTMLResponse)
def trainers(
    request: Request,
    search: str = "",
    status: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("trainers.read")),
):
    rows, total = DomainRepository(db).trainers(search, status, max(page, 1))
    members = list(db.scalars(select(Member).where(Member.status == "active").order_by(Member.full_name)))
    return templates.TemplateResponse(
        request,
        "trainers.html",
        context(
            request, user, title="Trainers", trainers=rows, members=members, total=total, search=search, status=status
        ),
    )


@router.post("/trainers")
def trainer_create(
    request: Request,
    csrf_token: str = Form(...),
    full_name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(""),
    specialization: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("trainers.write")),
):
    validate_csrf_value(request, csrf_token)
    try:
        DomainService(db).create_trainer(
            TrainerInput(
                full_name=full_name,
                phone=phone,
                email=email or None,
                specialization=specialization or None,
                notes=notes or None,
            )
        )
    except (ValidationError, Conflict, NotFound) as exc:
        raise HTTPException(409, form_error(exc)) from exc
    return RedirectResponse("/trainers", 303)


@router.post("/trainer-assignments")
def trainer_assign(
    request: Request,
    csrf_token: str = Form(...),
    trainer_id: int = Form(...),
    member_id: int = Form(...),
    start_date: date = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("trainers.write")),
):
    validate_csrf_value(request, csrf_token)
    try:
        DomainService(db).assign_trainer(
            AssignmentInput(trainer_id=trainer_id, member_id=member_id, start_date=start_date)
        )
    except (ValidationError, Conflict, NotFound) as exc:
        raise HTTPException(409, form_error(exc)) from exc
    return RedirectResponse("/trainers", 303)


@router.get("/workouts", response_class=HTMLResponse)
def workouts(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("workouts.read"))
):
    rows = list(
        db.scalars(
            select(WorkoutPlan)
            .options(selectinload(WorkoutPlan.member), selectinload(WorkoutPlan.trainer))
            .order_by(WorkoutPlan.id.desc())
        )
    )
    return templates.TemplateResponse(
        request,
        "workouts.html",
        context(
            request,
            user,
            title="Workouts",
            workouts=rows,
            members=list(db.scalars(select(Member).where(Member.status == "active").order_by(Member.full_name))),
            trainers=list(db.scalars(select(Trainer).where(Trainer.status == "active").order_by(Trainer.full_name))),
            exercises=list(db.scalars(select(Exercise).where(Exercise.is_active.is_(True)).order_by(Exercise.name))),
        ),
    )


@router.post("/exercises")
def exercise_create(
    request: Request,
    csrf_token: str = Form(...),
    name: str = Form(...),
    muscle_group: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workouts.write")),
):
    validate_csrf_value(request, csrf_token)
    try:
        DomainService(db).create_exercise(
            ExerciseInput(name=name, muscle_group=muscle_group or None, description=description or None)
        )
    except (ValidationError, Conflict, NotFound) as exc:
        raise HTTPException(409, form_error(exc)) from exc
    return RedirectResponse("/workouts", 303)


@router.post("/workouts")
def workout_create(
    request: Request,
    csrf_token: str = Form(...),
    name: str = Form(...),
    member_id: int = Form(...),
    trainer_id: int = Form(...),
    start_date: date = Form(...),
    end_date: date | None = Form(None),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workouts.write")),
):
    validate_csrf_value(request, csrf_token)
    try:
        DomainService(db).create_workout(
            WorkoutInput(
                name=name,
                member_id=member_id,
                trainer_id=trainer_id,
                start_date=start_date,
                end_date=end_date,
                notes=notes or None,
            )
        )
    except (ValidationError, Conflict, NotFound) as exc:
        raise HTTPException(409, form_error(exc)) from exc
    return RedirectResponse("/workouts", 303)


@router.post("/workouts/{workout_id}/exercises")
def workout_exercise_create(
    workout_id: int,
    request: Request,
    csrf_token: str = Form(...),
    exercise_id: int = Form(...),
    position: int = Form(...),
    sets: int = Form(...),
    reps: int = Form(...),
    weight: Decimal | None = Form(None),
    rest_seconds: int | None = Form(None),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("workouts.write")),
):
    validate_csrf_value(request, csrf_token)
    try:
        DomainService(db).add_workout_exercise(
            workout_id,
            WorkoutExerciseInput(
                exercise_id=exercise_id,
                position=position,
                sets=sets,
                reps=reps,
                weight=weight,
                rest_seconds=rest_seconds,
                notes=notes or None,
            ),
        )
    except (ValidationError, Conflict, NotFound) as exc:
        raise HTTPException(409, form_error(exc)) from exc
    return RedirectResponse("/workouts", 303)


@router.get("/reports", response_class=HTMLResponse)
def reports(
    request: Request,
    kind: str = "active-members",
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("reports.read")),
):
    try:
        rows = ReportingService(db).report_rows(kind, start, end)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return templates.TemplateResponse(
        request, "reports.html", context(request, user, title="Reports", kind=kind, rows=rows, start=start, end=end)
    )


@router.get("/reports/{kind}.csv")
def report_csv(
    kind: str,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("reports.read")),
):
    try:
        rows = ReportingService(db).report_rows(kind, start, end)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    stream = io.StringIO(newline="")
    stream.write("\ufeff")
    csv.writer(stream).writerows(rows)
    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'},
    )


@router.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("users.manage"))
):
    users = list(db.scalars(select(User).options(selectinload(User.role)).order_by(User.username)))
    return templates.TemplateResponse(request, "users.html", context(request, user, title="Users", users=users))


@router.post("/users")
def user_create(
    request: Request,
    csrf_token: str = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role_name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users.manage")),
):
    validate_csrf_value(request, csrf_token)
    try:
        UserAdminService(db).create(
            StaffUserInput(
                username=username,
                email=email,
                password=password,
                role_name=role_name,
            )
        )
    except (ValidationError, Conflict, NotFound) as exc:
        raise HTTPException(409, form_error(exc)) from exc
    return RedirectResponse("/users", 303)


@router.post("/users/{user_id}/status")
def user_toggle(
    user_id: int,
    request: Request,
    csrf_token: str = Form(...),
    active: bool = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users.manage")),
):
    validate_csrf_value(request, csrf_token)
    try:
        UserAdminService(db).set_active(user_id, active, user.id)
    except (Conflict, NotFound) as exc:
        raise HTTPException(409, str(exc)) from exc
    return RedirectResponse("/users", 303)


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, user: User = Depends(require_permission("settings.manage"))):
    return templates.TemplateResponse(request, "settings.html", context(request, user, title="Settings"))
