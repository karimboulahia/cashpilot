"""Transaction service — CRUD and aggregation for income/expense tracking."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate


async def create_transaction(
    db: AsyncSession, user_id: int, data: TransactionCreate
) -> Transaction:
    """Create a new transaction."""
    tx = Transaction(
        user_id=user_id,
        account_id=data.account_id,
        amount=data.amount,
        category=data.category.value,
        description=data.description,
        transaction_type=data.transaction_type.value,
    )
    db.add(tx)
    await db.flush()
    await db.refresh(tx)
    return tx


async def get_user_transactions(
    db: AsyncSession,
    user_id: int,
    limit: int = 50,
    days: int | None = None,
) -> list[Transaction]:
    """Get recent transactions for a user."""
    query = select(Transaction).where(Transaction.user_id == user_id)
    if days:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.where(Transaction.transaction_date >= since)
    query = query.order_by(Transaction.transaction_date.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_monthly_spending(
    db: AsyncSession, user_id: int, months: int = 1
) -> Decimal:
    """Get total spending for the last N months."""
    since = datetime.now(timezone.utc) - timedelta(days=months * 30)
    result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.user_id == user_id)
        .where(Transaction.transaction_type == "expense")
        .where(Transaction.transaction_date >= since)
    )
    return Decimal(str(result.scalar() or 0))


async def get_spending_by_category(
    db: AsyncSession, user_id: int, days: int = 30
) -> list[dict]:
    """Get spending breakdown by category for the last N days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count().label("count"),
        )
        .where(Transaction.user_id == user_id)
        .where(Transaction.transaction_type == "expense")
        .where(Transaction.transaction_date >= since)
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
    )
    return [
        {"category": row.category, "total": Decimal(str(row.total)), "count": row.count}
        for row in result.all()
    ]


async def get_spending_trend(
    db: AsyncSession, user_id: int
) -> str:
    """Compare last 30 days vs previous 30 days to detect spending trend."""
    now = datetime.now(timezone.utc)
    last_30 = await _period_spending(db, user_id, now - timedelta(days=30), now)
    prev_30 = await _period_spending(
        db, user_id, now - timedelta(days=60), now - timedelta(days=30)
    )

    if prev_30 == 0:
        return "stable"
    change = (last_30 - prev_30) / prev_30
    if change > Decimal("0.15"):
        return "increasing"
    if change < Decimal("-0.15"):
        return "decreasing"
    return "stable"


async def _period_spending(
    db: AsyncSession, user_id: int, start: datetime, end: datetime
) -> Decimal:
    result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.user_id == user_id)
        .where(Transaction.transaction_type == "expense")
        .where(Transaction.transaction_date >= start)
        .where(Transaction.transaction_date <= end)
    )
    return Decimal(str(result.scalar() or 0))


async def get_last_transaction(
    db: AsyncSession, user_id: int
) -> Transaction | None:
    """Get the most recent transaction for a user (for corrections/cancellations)."""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.transaction_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def delete_transaction(
    db: AsyncSession, transaction_id: int
) -> bool:
    """Delete a transaction by ID. Returns True if deleted."""
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    tx = result.scalar_one_or_none()
    if tx:
        await db.delete(tx)
        await db.flush()
        return True
    return False


async def update_transaction_amount(
    db: AsyncSession, transaction_id: int, new_amount: Decimal
) -> Transaction | None:
    """Update the amount of a transaction (for corrections)."""
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    tx = result.scalar_one_or_none()
    if tx:
        tx.amount = new_amount
        await db.flush()
        await db.refresh(tx)
        return tx
    return None
