"""Goal schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class GoalCreate(BaseModel):
    name: str
    target_amount: Decimal
    current_amount: Decimal = Decimal("0")
    deadline_months: int | None = None
    priority: int = 1


class GoalUpdate(BaseModel):
    current_amount: Decimal | None = None
    is_active: bool | None = None


class GoalResponse(BaseModel):
    id: int
    user_id: int
    name: str
    target_amount: Decimal
    current_amount: Decimal
    deadline_months: int | None
    priority: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
