"""Goal endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.db.models.goal import Goal
from app.db.session import get_db
from app.schemas.goal import GoalCreate, GoalResponse
from app.services.profile_service import get_user_by_id

router = APIRouter(prefix="/goals", tags=["goals"], dependencies=[Depends(verify_api_key)])


@router.post("", response_model=GoalResponse, status_code=201)
async def create_goal(
    user_id: int, data: GoalCreate, db: AsyncSession = Depends(get_db)
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    goal = Goal(
        user_id=user.id,
        name=data.name,
        target_amount=data.target_amount,
        current_amount=data.current_amount,
        deadline_months=data.deadline_months,
        priority=data.priority,
    )
    db.add(goal)
    await db.flush()
    await db.refresh(goal)
    return goal


@router.get("/user/{user_id}", response_model=list[GoalResponse])
async def get_user_goals(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    result = await db.execute(
        select(Goal).where(Goal.user_id == user.id).where(Goal.is_active.is_(True))
    )
    return list(result.scalars().all())
