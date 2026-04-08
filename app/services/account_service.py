"""Account service — CRUD operations for user accounts."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account import Account
from app.schemas.account import AccountCreate, AccountUpdate


async def create_account(
    db: AsyncSession, user_id: int, data: AccountCreate
) -> Account:
    """Create a new account for a user."""
    account = Account(
        user_id=user_id,
        name=data.name,
        account_type=data.account_type.value,
        balance=data.balance,
        currency=data.currency,
    )
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


async def get_user_accounts(
    db: AsyncSession, user_id: int, active_only: bool = True
) -> list[Account]:
    """Get all accounts for a user."""
    query = select(Account).where(Account.user_id == user_id)
    if active_only:
        query = query.where(Account.is_active.is_(True))
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_account(
    db: AsyncSession, account_id: int, data: AccountUpdate
) -> Account | None:
    """Update an account."""
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        return None
    if data.name is not None:
        account.name = data.name
    if data.balance is not None:
        account.balance = data.balance
    if data.is_active is not None:
        account.is_active = data.is_active
    await db.flush()
    await db.refresh(account)
    return account


async def get_total_liquid_cash(db: AsyncSession, user_id: int) -> Decimal:
    """Calculate total liquid cash across all active accounts."""
    liquid_types = {"bank", "neo_bank", "cash", "paypal"}
    accounts = await get_user_accounts(db, user_id)
    return sum(
        (a.balance for a in accounts if a.account_type in liquid_types),
        Decimal("0"),
    )


async def get_total_patrimony(db: AsyncSession, user_id: int) -> Decimal:
    """Calculate total patrimony across all active accounts."""
    accounts = await get_user_accounts(db, user_id)
    return sum((a.balance for a in accounts), Decimal("0"))


async def get_account_breakdown(
    db: AsyncSession, user_id: int
) -> dict[str, Decimal]:
    """Get balance breakdown by account type."""
    accounts = await get_user_accounts(db, user_id)
    breakdown: dict[str, Decimal] = {}
    for account in accounts:
        key = account.account_type
        breakdown[key] = breakdown.get(key, Decimal("0")) + account.balance
    return breakdown
