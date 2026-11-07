"""Contact form rate limits: ``support_limits``."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlmodel import Field

from app.models.base import Base


class SupportLimit(Base, table=True):
    """
    Contact form use per hashed IP or email in the current window.
    Firestore: ``supportLimits/{key}``.
    """

    __tablename__ = "support_limits"

    key: str = Field(primary_key=True, sa_type=Text)
    window_start: datetime = Field(nullable=False, sa_type=DateTime(timezone=True))
    count: int = Field(default=0, nullable=False, sa_type=Integer)
