"""Profile service — CRUD for financial profiles."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.financial_profile import FinancialProfile
from app.db.models.user import User
from app.schemas.financial_profile import FinancialProfileCreate, FinancialProfileUpdate


async def get_or_create_user(
    db: AsyncSession, telegram_id: int, **kwargs
) -> User:
    """Get existing user or create a new one."""
    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        return user

    user = User(telegram_id=telegram_id, **kwargs)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def get_user_by_telegram_id(
    db: AsyncSession, telegram_id: int
) -> User | None:
    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_or_create_profile(
    db: AsyncSession, user_id: int
) -> FinancialProfile:
    """Get existing profile or create an empty one."""
    result = await db.execute(
        select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile:
        return profile

    profile = FinancialProfile(user_id=user_id)
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    return profile


async def update_profile(
    db: AsyncSession, user_id: int, data: FinancialProfileUpdate
) -> FinancialProfile:
    """Update a user's financial profile."""
    profile = await get_or_create_profile(db, user_id)
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(profile, key, value)
    await db.flush()
    await db.refresh(profile)
    return profile


async def update_profile_field(
    db: AsyncSession, user_id: int, field_name: str, value
) -> FinancialProfile:
    """Update a single field on the financial profile."""
    profile = await get_or_create_profile(db, user_id)
    setattr(profile, field_name, value)
    await db.flush()
    await db.refresh(profile)
    return profile


async def mark_onboarding_complete(db: AsyncSession, user_id: int) -> None:
    """Mark user onboarding as completed."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.onboarding_completed = True
        await db.flush()
