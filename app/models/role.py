from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin
from app.models.role_permission import role_permissions


class Role(TimestampMixin, Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    users: Mapped[list["User"]] = relationship(back_populates="role", passive_deletes="all")
    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions, back_populates="roles", passive_deletes=True
    )
