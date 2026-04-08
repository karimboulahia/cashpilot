"""Transaction endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.db.session import get_db
from app.schemas.transaction import TransactionCreate, TransactionResponse
from app.services import transaction_service
from app.services.profile_service import get_user_by_id

router = APIRouter(prefix="/transactions", tags=["transactions"], dependencies=[Depends(verify_api_key)])


@router.post("", response_model=TransactionResponse, status_code=201)
async def create_transaction(
    user_id: int, data: TransactionCreate, db: AsyncSession = Depends(get_db)
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    tx = await transaction_service.create_transaction(db, user.id, data)
    return tx


@router.get("/user/{user_id}", response_model=list[TransactionResponse])
async def get_user_transactions(
    user_id: int,
    limit: int = 50,
    days: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return await transaction_service.get_user_transactions(db, user.id, limit=limit, days=days)
