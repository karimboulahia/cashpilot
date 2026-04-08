"""Telegram service — orchestrator that bridges Telegram messages to backend services."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.user import User
from app.schemas.account import AccountCreate, AccountType
from app.schemas.transaction import TransactionCreate, TransactionCategory, TransactionType
from app.services import (
    account_service,
    transaction_service,
    profile_service,
    reporting_service,
)
from app.services.decision_engine import (
    UserFinancialSnapshot,
    PurchaseInput,
    evaluate_purchase,
    get_missing_questions,
)
from app.services.llm_service import classify_intent, reformulate_decision, generate_follow_up_questions
from app.services.onboarding_service import (
    OnboardingStep,
    ONBOARDING_QUESTIONS,
    get_next_step,
    should_ask_income_end_date,
    parse_income_type,
    parse_housing_situation,
    parse_safety_months,
    parse_main_goal,
    parse_risk_tolerance,
    parse_amount,
)
from app.services.parser_service import parse_expense

logger = get_logger("telegram_service")

# In-memory onboarding state (per user)
# In production, use Redis or DB
_onboarding_state: dict[int, str] = {}


async def handle_message(
    db: AsyncSession, user: User, text: str
) -> str:
    """Main message handler — routes to appropriate service."""

    # If user is in onboarding
    if not user.onboarding_completed:
        return await _handle_onboarding(db, user, text)

    # Classify intent
    intent_result = await classify_intent(text)
    intent = intent_result.get("intent", "unknown")
    entities = intent_result.get("entities", {})

    logger.info(f"Intent: {intent} for user {user.telegram_id}")

    if intent == "add_expense":
        return await _handle_add_expense(db, user, text)
    elif intent == "ask_purchase_decision":
        return await _handle_purchase_decision(db, user, text, entities)
    elif intent == "show_summary":
        return await _handle_summary(db, user)
    elif intent == "add_account":
        return "Pour ajouter un compte, utilise /add_account 🏦"
    elif intent == "update_profile":
        return "Pour modifier ton profil, utilise /profile ✏️"
    else:
        # Try expense parsing as fallback
        parsed = parse_expense(text)
        if parsed:
            return await _handle_add_expense(db, user, text)
        return (
            "🤔 Je n'ai pas compris. Tu peux :\n"
            "• Noter une dépense : \"25 resto\"\n"
            "• Demander un avis : /canibuy\n"
            "• Voir ton résumé : /summary"
        )


async def _handle_onboarding(
    db: AsyncSession, user: User, text: str
) -> str:
    """Handle onboarding step by step."""
    current_step = _onboarding_state.get(user.telegram_id, OnboardingStep.WELCOME)

    if current_step == OnboardingStep.WELCOME:
        _onboarding_state[user.telegram_id] = OnboardingStep.MONTHLY_INCOME
        return ONBOARDING_QUESTIONS[OnboardingStep.WELCOME]

    profile = await profile_service.get_or_create_profile(db, user.id)

    try:
        step = OnboardingStep(current_step)
    except ValueError:
        step = OnboardingStep.MONTHLY_INCOME

    # Process answer for current step
    if step == OnboardingStep.MONTHLY_INCOME:
        amount = parse_amount(text)
        await profile_service.update_profile_field(db, user.id, "monthly_income", Decimal(str(amount)))
        next_step = OnboardingStep.INCOME_TYPE

    elif step == OnboardingStep.INCOME_TYPE:
        income_type = parse_income_type(text)
        await profile_service.update_profile_field(db, user.id, "income_type", income_type)
        if should_ask_income_end_date(income_type):
            next_step = OnboardingStep.INCOME_END_DATE
        else:
            next_step = OnboardingStep.MONTHLY_CHARGES

    elif step == OnboardingStep.INCOME_END_DATE:
        await profile_service.update_profile_field(db, user.id, "income_end_date", text.strip())
        next_step = OnboardingStep.MONTHLY_CHARGES

    elif step == OnboardingStep.MONTHLY_CHARGES:
        amount = parse_amount(text)
        await profile_service.update_profile_field(db, user.id, "monthly_fixed_charges", Decimal(str(amount)))
        next_step = OnboardingStep.AVAILABLE_SAVINGS

    elif step == OnboardingStep.AVAILABLE_SAVINGS:
        amount = parse_amount(text)
        await profile_service.update_profile_field(db, user.id, "available_savings", Decimal(str(amount)))
        next_step = OnboardingStep.TOTAL_DEBT

    elif step == OnboardingStep.TOTAL_DEBT:
        amount = parse_amount(text)
        await profile_service.update_profile_field(db, user.id, "total_debt", Decimal(str(amount)))
        next_step = OnboardingStep.HOUSING_SITUATION

    elif step == OnboardingStep.HOUSING_SITUATION:
        housing = parse_housing_situation(text)
        await profile_service.update_profile_field(db, user.id, "housing_situation", housing)
        next_step = OnboardingStep.SAFETY_NET_MONTHS

    elif step == OnboardingStep.SAFETY_NET_MONTHS:
        months = parse_safety_months(text)
        await profile_service.update_profile_field(db, user.id, "safety_net_months", months)
        next_step = OnboardingStep.MAIN_GOAL

    elif step == OnboardingStep.MAIN_GOAL:
        goal = parse_main_goal(text)
        await profile_service.update_profile_field(db, user.id, "main_goal", goal)
        next_step = OnboardingStep.RISK_TOLERANCE

    elif step == OnboardingStep.RISK_TOLERANCE:
        risk = parse_risk_tolerance(text)
        await profile_service.update_profile_field(db, user.id, "risk_tolerance", risk)
        await profile_service.mark_onboarding_complete(db, user.id)
        _onboarding_state.pop(user.telegram_id, None)
        return ONBOARDING_QUESTIONS[OnboardingStep.COMPLETED]

    else:
        next_step = OnboardingStep.MONTHLY_INCOME

    _onboarding_state[user.telegram_id] = next_step.value
    return ONBOARDING_QUESTIONS.get(next_step, "❓")


async def _handle_add_expense(
    db: AsyncSession, user: User, text: str
) -> str:
    """Parse and record an expense from free text."""
    parsed = parse_expense(text)
    if not parsed:
        return "❌ Je n'ai pas compris le montant. Essaie : \"25 resto\" ou \"18 uber\""

    # Map category string to enum
    try:
        category = TransactionCategory(parsed.category)
    except ValueError:
        category = TransactionCategory.AUTRE

    tx_type = TransactionType.INCOME if parsed.is_income else TransactionType.EXPENSE

    tx_data = TransactionCreate(
        amount=Decimal(str(parsed.amount)),
        category=category,
        description=parsed.description,
        transaction_type=tx_type,
    )
    tx = await transaction_service.create_transaction(db, user.id, tx_data)

    emoji = "📥" if parsed.is_income else "📤"
    return (
        f"{emoji} *{parsed.amount:.2f}€* — {parsed.category}\n"
        f"_{parsed.description}_\n"
        f"✅ Enregistré !"
    )


async def _handle_purchase_decision(
    db: AsyncSession, user: User, text: str, entities: dict
) -> str:
    """Evaluate a purchase decision."""
    # Extract purchase info from entities or text
    item_name = entities.get("item_name", text)
    price = entities.get("price")
    category = entities.get("category", "autre")

    if not price:
        return (
            "💰 Pour évaluer un achat, j'ai besoin de :\n"
            "• Le nom de l'article\n"
            "• Le prix\n\n"
            "Exemple : \"Est-ce que je peux acheter un iPhone à 1200€ ?\""
        )

    # Build snapshot
    snapshot = await _build_financial_snapshot(db, user)
    purchase = PurchaseInput(
        item_name=str(item_name),
        price=Decimal(str(price)),
        item_category=str(category),
    )

    # Check for missing info first
    missing = get_missing_questions(snapshot, purchase)
    if missing and snapshot.monthly_income == 0:
        questions_text = await generate_follow_up_questions(missing)
        return f"🤔 Avant de décider, j'ai besoin de quelques infos :\n\n{questions_text}"

    # Run decision engine
    result = evaluate_purchase(snapshot, purchase)

    # Reformulate with LLM
    decision_data = result.model_dump()
    decision_data["price"] = str(price)
    decision_data["item_name"] = str(item_name)

    response = await reformulate_decision(
        decision_data,
        user_context=f"Revenu: {snapshot.monthly_income}€, Épargne: {snapshot.available_savings}€",
    )
    return response


async def _handle_summary(db: AsyncSession, user: User) -> str:
    """Generate and return financial summary."""
    summary = await reporting_service.get_financial_summary(db, user)
    return reporting_service.format_summary_message(summary)


async def _build_financial_snapshot(
    db: AsyncSession, user: User
) -> UserFinancialSnapshot:
    """Build a complete financial snapshot for the decision engine."""
    profile = await profile_service.get_or_create_profile(db, user.id)
    total_liquid = await account_service.get_total_liquid_cash(db, user.id)
    total_patrimony = await account_service.get_total_patrimony(db, user.id)
    monthly_spending = await transaction_service.get_monthly_spending(db, user.id)
    spending_trend = await transaction_service.get_spending_trend(db, user.id)
    top_categories = await transaction_service.get_spending_by_category(db, user.id)

    # Build active goals
    from app.db.models.goal import Goal
    from sqlalchemy import select
    result = await db.execute(
        select(Goal).where(Goal.user_id == user.id).where(Goal.is_active.is_(True))
    )
    goals = result.scalars().all()
    active_goals = [
        {
            "name": g.name,
            "remaining": str(g.remaining),
            "deadline_months": g.deadline_months,
        }
        for g in goals
    ]

    return UserFinancialSnapshot(
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
        top_spending_categories=[
            {"category": c["category"], "total": str(c["total"])}
            for c in top_categories
        ],
        active_goals=active_goals,
    )
