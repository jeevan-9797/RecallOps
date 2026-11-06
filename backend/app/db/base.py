"""
SQLAlchemy 2.0 Declarative Base and Model Mixins.
"""

from datetime import datetime, timezone
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarative class for all RecallOps database models."""
    pass


class TimestampMixin:
    """Reusable mixin providing created_at timestamp in UTC."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
