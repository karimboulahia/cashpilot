"""Database models package — import all models here for Alembic discovery."""

from app.db.models.user import User
from app.db.models.financial_profile import FinancialProfile
from app.db.models.account import Account
from app.db.models.transaction import Transaction
from app.db.models.goal import Goal
from app.db.models.purchase_decision import PurchaseDecision

__all__ = [
    "User",
    "FinancialProfile",
    "Account",
    "Transaction",
    "Goal",
    "PurchaseDecision",
]
