"""API shapes for a user's profile and settings (/api/profile)."""

import re
from datetime import datetime
from typing import Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel


_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


class LinkedAuthorEntry(SQLModel):
    id: str
    name: Optional[str] = None


class UserProfile(SQLModel):
    uid: str
    email: str
    display_name: Optional[str] = None
    notification_email: Optional[str] = None
    # True while a custom notification_email awaits confirmation; mail goes
    # to the account email until then.
    notification_email_pending: bool = False
    notify_enabled: bool = True
    notify_new_publications: bool = True
    scholar_url: Optional[str] = None
    linked_author_id: Optional[str] = None
    linked_author_name: Optional[str] = None
    additional_linked_authors: list[LinkedAuthorEntry] = Field(default_factory=list)
    name_aliases: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class UpdateProfileRequest(SQLModel):
    display_name: Optional[str] = Field(default=None, max_length=120)
    notification_email: Optional[str] = Field(default=None, max_length=254)
    notify_enabled: Optional[bool] = None
    notify_new_publications: Optional[bool] = None
    scholar_url: Optional[str] = Field(default=None, max_length=500)
    name_aliases: Optional[list[str]] = None

    @field_validator("notification_email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v and not _EMAIL_RE.match(v):
            raise ValueError("Invalid email address.")
        return v

    @field_validator("scholar_url")
    @classmethod
    def validate_scholar_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not _URL_RE.match(v):
            raise ValueError("Scholar URL must start with http:// or https://.")
        return v

    @field_validator("name_aliases")
    @classmethod
    def validate_aliases(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        if len(v) > 20:
            raise ValueError("Maximum 20 name aliases allowed.")
        for alias in v:
            if len(alias) > 100:
                raise ValueError("Each alias must be 100 characters or fewer.")
        return v
