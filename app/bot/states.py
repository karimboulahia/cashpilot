"""Conversation states for multi-step flows."""

from enum import IntEnum, auto


class OnboardingState(IntEnum):
    """States for the onboarding conversation flow."""
    MONTHLY_INCOME = auto()
    INCOME_TYPE = auto()
    INCOME_END_DATE = auto()
    MONTHLY_CHARGES = auto()
    AVAILABLE_SAVINGS = auto()
    TOTAL_DEBT = auto()
    HOUSING_SITUATION = auto()
    SAFETY_NET = auto()
    MAIN_GOAL = auto()
    RISK_TOLERANCE = auto()


class PurchaseDecisionState(IntEnum):
    """States for the purchase decision flow."""
    ITEM_NAME = auto()
    ITEM_PRICE = auto()
    ESSENTIALITY = auto()
    RECURRING_COSTS = auto()
    CONFIRM = auto()


class AddAccountState(IntEnum):
    """States for the add account flow."""
    ACCOUNT_NAME = auto()
    ACCOUNT_TYPE = auto()
    ACCOUNT_BALANCE = auto()
