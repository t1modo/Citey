"""An account: ``users``."""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship

from app.models.base import Base, created_at_column, flag_column, text_array_column, timestamp_column

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.work import UserWork


class User(Base, table=True):
    """One account."""

    __tablename__ = "users"

    # The Clerk user ID ("user_..."), the session token's sub.
    id: str = Field(primary_key=True, max_length=128)
    email: str = Field(
        default="", nullable=False, sa_type=Text, sa_column_kwargs={"server_default": text("''")}
    )
    display_name: Optional[str] = Field(default=None, sa_type=Text)

    # Alerts go to notification_email once it is confirmed, and to the
    # account email until then.
    notification_email: Optional[str] = Field(default=None, sa_type=Text)
    verified_notification_email: Optional[str] = Field(default=None, sa_type=Text)
    notify_enabled: bool = flag_column(True)
    notify_new_publications: bool = flag_column(True)

    scholar_url: Optional[str] = Field(default=None, sa_type=Text)
    # The author profile (OpenAlex, Semantic Scholar, INSPIRE or DBLP ID)
    # whose papers this user tracks, plus any profiles merged into it as
    # [{"id": ..., "name": ...}].
    linked_author_id: Optional[str] = Field(default=None, sa_type=Text, index=True)
    linked_author_name: Optional[str] = Field(default=None, sa_type=Text)
    additional_linked_authors: list[dict[str, Any]] = Field(
        default_factory=list,
        nullable=False,
        sa_type=JSONB,
        sa_column_kwargs={"server_default": text("'[]'::jsonb")},
    )
    name_aliases: list[str] = text_array_column()
    # works.key values the user removed, so publication sync doesn't add
    # them back.
    dismissed_work_keys: list[str] = text_array_column()

    # Cooldowns and bookkeeping.
    last_import_at: Optional[datetime] = timestamp_column()
    last_manual_check_at: Optional[datetime] = timestamp_column()
    last_manual_sync_at: Optional[datetime] = timestamp_column()
    last_publication_sync_at: Optional[datetime] = timestamp_column()
    last_email_test_at: Optional[datetime] = timestamp_column()
    last_verification_email_at: Optional[datetime] = timestamp_column()
    last_confirm_email_at: Optional[datetime] = timestamp_column()

    created_at: datetime = created_at_column()

    tracked: list["UserWork"] = Relationship(
        back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True}
    )
    alerts: list["Alert"] = Relationship(
        back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True}
    )
