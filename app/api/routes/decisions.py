"""Decision evaluation endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.db.session import get_db
from app.schemas.purchase_decision import PurchaseRequest, DecisionResult
from app.services.decision_engine import UserFinancialSnapshot, PurchaseInput, evaluate_purchase
from app.services.profile_service import get_user_by_id, get_or_create_profile
from app.services import account_service, transaction_service

router = APIRouter(prefix="/decisions", tags=["decisions"], dependencies=[Depends(verify_api_key)])


@router.post("/evaluate", response_model=DecisionResult)
async def evaluate_purchase_endpoint(
    user_id: int,
    data: PurchaseRequest,
    db: AsyncSession = Depends(get_db),
):
    """Evaluate a purchase decision using the backend rules engine."""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = await get_or_create_profile(db, user.id)
    total_liquid = await account_service.get_total_liquid_cash(db, user.id)
    total_patrimony = await account_service.get_total_patrimony(db, user.id)
    monthly_spending = await transaction_service.get_monthly_spending(db, user.id)
    spending_trend = await transaction_service.get_spending_trend(db, user.id)

    snapshot = UserFinancialSnapshot(
        monthly_income=profile.monthly_income,
        income_type=profile.income_type,
        income_end_date=profile.income_end_date,
        monthly_fixed_charges=profile.monthly_fixed_charges,
        available_savings=profile.available_savings,
        total_debt=profile.total_debt,
        safety_net_months=profile.safety_net_months,
        main_goal=profile.main_goal,
        risk_tolerance=profile.risk_tolerance,
        total_liquid_cash=total_liquid if total_liquid > 0 else profile.available_savings,
        total_patrimony=total_patrimony if total_patrimony > 0 else profile.available_savings,
        monthly_spending_avg=monthly_spending,
        spending_trend=spending_trend,
    )

    purchase = PurchaseInput(
        item_name=data.item_name,
        price=data.price,
        item_category=data.item_category or "autre",
        payment_type=data.payment_type.value,
        essentiality=data.essentiality.value,
        recurring_cost_estimate=data.recurring_cost_estimate,
    )

    result = evaluate_purchase(snapshot, purchase)
    return result
