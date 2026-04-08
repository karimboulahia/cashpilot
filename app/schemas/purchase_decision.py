"""Purchase decision schemas — input request and structured output."""

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class DecisionStatus(str, Enum):
    YES = "YES"
    NO = "NO"
    WAIT = "WAIT"
    CONDITIONAL = "CONDITIONAL"


class Essentiality(str, Enum):
    ESSENTIAL = "essential"
    USEFUL = "useful"
    COMFORT = "comfort"
    IMPULSE = "impulse"


class PaymentType(str, Enum):
    CASH = "cash"
    INSTALLMENTS = "installments"


class PurchaseRequest(BaseModel):
    """What the user wants to buy."""
    item_name: str
    item_category: str | None = None
    price: Decimal
    payment_type: PaymentType = PaymentType.CASH
    essentiality: Essentiality = Essentiality.COMFORT
    recurring_cost_estimate: Decimal = Decimal("0")
    target_account_id: int | None = None


class DecisionResult(BaseModel):
    """Structured output from the decision engine."""
    decision_status: DecisionStatus
    confidence_score: int = Field(ge=0, le=100)
    risk_score: int = Field(ge=0, le=100)
    recommended_max_budget: Decimal | None = None
    main_reason: str
    risk_factors: list[str] = []
    positives: list[str] = []
    missing_information: list[str] = []
    explanation_short: str
    explanation_detailed: str
    alternative_suggestion: str | None = None


class PurchaseDecisionResponse(BaseModel):
    """Full response including request + decision."""
    id: int
    item_name: str
    price: Decimal
    decision_status: str
    confidence_score: int
    risk_score: int
    recommended_max_budget: Decimal | None
    main_reason: str
    explanation_short: str

    model_config = {"from_attributes": True}
