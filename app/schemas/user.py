"""User schemas."""

from datetime import datetime
from pydantic import BaseModel


class UserCreate(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str = "fr"


class UserResponse(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str
    is_active: bool
    onboarding_completed: bool
    created_at: datetime

    model_config = {"from_attributes": True}
