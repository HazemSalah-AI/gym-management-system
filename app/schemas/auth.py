from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from app.core.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    username: str = Field(min_length=1, max_length=50)
    password: SecretStr = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class AdminInput(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-z0-9_.-]+$")
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("username", "email", mode="before")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("email")
    @classmethod
    def normalize_validated_email(cls, value: str) -> str:
        return value.lower()


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str
    is_active: bool
    role: RoleResponse
    last_login_at: datetime | None


class CsrfResponse(BaseModel):
    csrf_token: str
