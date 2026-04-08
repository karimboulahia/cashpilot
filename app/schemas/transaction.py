"""Transaction schemas."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel


class TransactionCategory(str, Enum):
    LOGEMENT = "logement"
    ALIMENTATION = "alimentation"
    TRANSPORT = "transport"
    LOISIR = "loisir"
    SANTE = "santé"
    ABONNEMENT = "abonnement"
    SHOPPING = "shopping"
    RESTAURANT = "restaurant"
    REVENU = "revenu"
    AUTRE = "autre"


class TransactionType(str, Enum):
    EXPENSE = "expense"
    INCOME = "income"


class TransactionCreate(BaseModel):
    amount: Decimal
    category: TransactionCategory
    description: str | None = None
    transaction_type: TransactionType = TransactionType.EXPENSE
    account_id: int | None = None


class TransactionResponse(BaseModel):
    id: int
    user_id: int
    account_id: int | None
    amount: Decimal
    category: str
    description: str | None
    transaction_type: str
    transaction_date: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
