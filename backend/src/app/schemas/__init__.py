"""
Pydantic request and response shapes for the API. The database tables are
in app.models.
"""

from app.schemas.job import JobRunRequest
from app.schemas.notification import Notification, PaginatedNotifications
from app.schemas.user import LinkedAuthorEntry, UpdateProfileRequest, UserProfile
from app.schemas.work import (
    AddWorkRequest,
    ImportByAuthorRequest,
    TrackedWork,
    is_openalex_work_id,
)

__all__ = [
    "AddWorkRequest",
    "ImportByAuthorRequest",
    "JobRunRequest",
    "LinkedAuthorEntry",
    "Notification",
    "PaginatedNotifications",
    "TrackedWork",
    "UpdateProfileRequest",
    "UserProfile",
    "is_openalex_work_id",
]
