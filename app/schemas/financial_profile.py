"""Financial profile schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class FinancialProfileCreate(BaseModel):
    monthly_income: Decimal = Decimal("0")
    income_type: str = "stable"
    income_end_date: str | None = None
    monthly_fixed_charges: Decimal = Decimal("0")
    available_savings: Decimal = Decimal("0")
    total_debt: Decimal = Decimal("0")
    housing_situation: str = "alone"
    safety_net_months: int = 3
    main_goal: str = "stability"
    risk_tolerance: str = "balanced"


class FinancialProfileUpdate(BaseModel):
    monthly_income: Decimal | None = None
    income_type: str | None = None
    income_end_date: str | None = None
    monthly_fixed_charges: Decimal | None = None
    available_savings: Decimal | None = None
    total_debt: Decimal | None = None
    housing_situation: str | None = None
    safety_net_months: int | None = None
    main_goal: str | None = None
    risk_tolerance: str | None = None


class FinancialProfileResponse(BaseModel):
    id: int
    user_id: int
    monthly_income: Decimal
    income_type: str
    income_end_date: str | None
    monthly_fixed_charges: Decimal
    available_savings: Decimal
    total_debt: Decimal
    housing_situation: str
    safety_net_months: int
    main_goal: str
    risk_tolerance: str
    created_at: datetime

    model_config = {"from_attributes": True}
