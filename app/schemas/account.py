"""Account schemas."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel


class AccountType(str, Enum):
    BANK = "bank"
    NEO_BANK = "neo_bank"
    SAVINGS = "savings"
    CASH = "cash"
    CRYPTO = "crypto"
    PAYPAL = "paypal"
    MEAL_VOUCHER = "meal_voucher"
    INVESTMENT = "investment"
    OTHER = "other"


class AccountCreate(BaseModel):
    name: str
    account_type: AccountType
    balance: Decimal = Decimal("0")
    currency: str = "EUR"


class AccountUpdate(BaseModel):
    name: str | None = None
    balance: Decimal | None = None
    is_active: bool | None = None


class AccountResponse(BaseModel):
    id: int
    user_id: int
    name: str
    account_type: str
    balance: Decimal
    currency: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
