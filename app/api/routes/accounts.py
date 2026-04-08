"""Account endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.db.session import get_db
from app.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from app.services import account_service
from app.services.profile_service import get_user_by_id

router = APIRouter(prefix="/accounts", tags=["accounts"], dependencies=[Depends(verify_api_key)])


@router.post("", response_model=AccountResponse, status_code=201)
async def create_account(
    user_id: int, data: AccountCreate, db: AsyncSession = Depends(get_db)
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    account = await account_service.create_account(db, user.id, data)
    return account


@router.get("/user/{user_id}", response_model=list[AccountResponse])
async def get_user_accounts(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return await account_service.get_user_accounts(db, user.id)
