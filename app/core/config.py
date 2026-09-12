from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    app_name: str = "Gym Management System"
    environment: Literal["development", "test", "production"] = "development"
    secret_key: SecretStr

    postgres_user: str
    postgres_password: SecretStr
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    gym_timezone: str = "Africa/Cairo"
    session_max_age: int = 28_800
    cookie_secure: bool | None = None

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def session_https_only(self) -> bool:
        return self.cookie_secure if self.cookie_secure is not None else self.environment == "production"

    @field_validator("gym_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("GYM_TIMEZONE must be a valid IANA timezone") from exc
        return value

    @field_validator("session_max_age")
    @classmethod
    def validate_session_age(cls, value: int) -> int:
        if not 300 <= value <= 86_400:
            raise ValueError("SESSION_MAX_AGE must be between 300 and 86400 seconds")
        return value

    @field_validator("secret_key")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if (
            len(raw) < 32
            or len(set(raw)) < 8
            or any(word in raw.lower() for word in ("change-this", "your-secret", "replace-me"))
        ):
            raise ValueError("SECRET_KEY must be a generated random secret of at least 32 characters")
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
    )


settings = Settings()
