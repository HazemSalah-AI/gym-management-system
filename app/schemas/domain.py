from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class MemberInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    phone: str = Field(min_length=7, max_length=30, pattern=r"^[0-9+() -]+$")
    email: EmailStr | None = None
    gender: str | None = None
    date_of_birth: date | None = None
    address: str | None = Field(default=None, max_length=500)
    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("full_name", "phone", mode="before")
    @classmethod
    def strip_required(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "email", "gender", "address", "emergency_contact_name", "emergency_contact_phone", "notes", mode="before"
    )
    @classmethod
    def empty_to_none(cls, value):
        return value.strip() if isinstance(value, str) and value.strip() else None

    @field_validator("date_of_birth")
    @classmethod
    def valid_birth_date(cls, value: date | None):
        if value and value >= date.today():
            raise ValueError("Date of birth must be in the past")
        return value


class MemberResponse(MemberInput):
    id: int
    member_number: str
    registration_date: date
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PlanInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    duration_months: int = Field(gt=0, le=120)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    description: str | None = Field(default=None, max_length=4000)


class SubscriptionInput(BaseModel):
    member_id: int = Field(gt=0)
    plan_id: int = Field(gt=0)
    requested_start_date: date = Field(default_factory=date.today)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)


class PaymentInput(BaseModel):
    member_id: int = Field(gt=0)
    subscription_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    method: str = Field(pattern=r"^(cash|card|bank_transfer)$")
    reference_number: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=4000)


class AttendanceInput(BaseModel):
    member_id: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=500)


class TrainerInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    phone: str = Field(min_length=7, max_length=30, pattern=r"^[0-9+() -]+$")
    email: EmailStr | None = None
    specialization: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(default=None, max_length=4000)


class AssignmentInput(BaseModel):
    trainer_id: int = Field(gt=0)
    member_id: int = Field(gt=0)
    start_date: date = Field(default_factory=date.today)


class ExerciseInput(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=4000)
    muscle_group: str | None = Field(default=None, max_length=100)


class WorkoutInput(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    member_id: int = Field(gt=0)
    trainer_id: int = Field(gt=0)
    start_date: date = Field(default_factory=date.today)
    end_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class WorkoutExerciseInput(BaseModel):
    exercise_id: int = Field(gt=0)
    position: int = Field(gt=0)
    sets: int = Field(gt=0, le=100)
    reps: int = Field(gt=0, le=1000)
    weight: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    rest_seconds: int | None = Field(default=None, ge=0, le=3600)
    notes: str | None = Field(default=None, max_length=500)
