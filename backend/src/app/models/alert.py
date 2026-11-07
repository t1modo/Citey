"""A citation as one user sees it: ``alerts``."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Index, UniqueConstraint, text
from sqlmodel import Field, Relationship

from app.models.base import Base, bigint_pk_column, cascade_fk_column, created_at_column, flag_column
from app.models.citation import Citation
from app.models.user import User


class Alert(Base, table=True):
    """
    A citation as one user sees it. Firestore: ``users/{uid}/notifications``.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("user_id", "citation_id"),
        Index(None, "user_id", "created_at"),
        Index(None, "citation_id"),
        # Small indexes for the two "what's left" queries.
        Index("ix_alerts_unseen", "user_id", postgresql_where=text("NOT seen")),
        Index("ix_alerts_unemailed", "user_id", postgresql_where=text("NOT emailed")),
    )

    id: Optional[int] = bigint_pk_column()
    user_id: str = Field(foreign_key="users.id", ondelete="CASCADE", nullable=False, max_length=128)
    citation_id: int = cascade_fk_column("citations.id")
    seen: bool = flag_column(False)
    # False until the alert email was actually sent, so a failed send is
    # retried on the next run instead of being lost.
    emailed: bool = flag_column(False)
    created_at: datetime = created_at_column()

    user: User = Relationship(back_populates="alerts")
    citation: Citation = Relationship(back_populates="alerts")
