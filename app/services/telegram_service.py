"""Telegram service — intelligent orchestrator bridging Telegram to backend services.

Uses LLM-powered NLU for intent detection and entity extraction,
DB-backed conversation context for multi-turn interactions,
and deterministic engines for financial decisions.

GUARDRAIL: The LLM NEVER makes financial decisions.
  - Intent/entity extraction: LLM (via ai_parser)
  - Clarification prompts: LLM (via llm_service)
  - Response reformulation: LLM (via llm_service)
  - Financial verdict (YES/NO/WAIT/CONDITIONAL): ONLY decision_engine.evaluate_purchase()
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionCategory, TransactionType
from app.services import (
    account_service,
    transaction_service,
    profile_service,
    reporting_service,
)
from app.services.ai_parser import parse_user_message, ParsedMessage
from app.services.context_service import (
    get_context,
    update_context,
    add_message_to_history,
    clear_pending_action,
    build_context_summary,
)
from app.services.decision_engine import (
    UserFinancialSnapshot,
    PurchaseInput,
    evaluate_purchase,
    get_missing_questions,
)
from app.services.llm_service import (
    reformulate_decision,
    generate_follow_up_questions,
    generate_conversational_response,
)
from app.services.onboarding_service import (
    OnboardingStep,
    ONBOARDING_QUESTIONS,
    should_ask_income_end_date,
)

logger = get_logger("telegram_service")

# Confidence thresholds
CONFIDENCE_HIGH = 0.75
CONFIDENCE_MEDIUM = 0.50


async def handle_message(
    db: AsyncSession, user: User, text: str
) -> str:
    """Main message handler — context-aware, AI-powered routing.

    NEVER raises. Always returns a user-facing string.
    """
    try:
        return await _handle_message_inner(db, user, text)
    except Exception as e:
        logger.error(f"[HANDLE] Unhandled error for user {user.telegram_id}: {type(e).__name__}: {e}", exc_info=True)
        return "⚠️ Oups, une erreur est survenue. Réessaie dans un instant !"


async def _handle_message_inner(
    db: AsyncSession, user: User, text: str
) -> str:
    """Inner handler — structured pipeline with logging."""
    logger.info(f"[HANDLE] user={user.telegram_id} message={text!r}")

    # ── 1. Load conversation context ─────────────────────
    ctx = await get_context(db, user.id)
    has_context = bool(ctx.last_intent or ctx.pending_action or ctx.last_item_name)
    logger.debug(
        f"[HANDLE] context: last_intent={ctx.last_intent} "
        f"pending={ctx.pending_action} last_item={ctx.last_item_name}"
    )

    # ── 2. Duplicate detection (Telegram retry) ──────────
    if await _is_duplicate_message(ctx, text):
        logger.info("[HANDLE] Duplicate message detected — skipping")
        return "✅ Déjà pris en compte !"

    # Save user message to history
    await add_message_to_history(db, user.id, "user", text)

    # ── 3. Handle onboarding (if not completed) ──────────
    if not user.onboarding_completed:
        logger.info(f"[HANDLE] routing to onboarding (step={ctx.onboarding_step})")
        response = await _handle_onboarding(db, user, text, ctx)
        await add_message_to_history(db, user.id, "assistant", response)
        return response

    # ── 4. Check for pending multi-turn action ───────────
    if ctx.pending_action:
        logger.info(f"[HANDLE] pending action: {ctx.pending_action}")
        response = await _handle_pending_action(db, user, text, ctx)
        if response:
            await add_message_to_history(db, user.id, "assistant", response)
            return response

    # ── 5. AI-powered intent detection ───────────────────
    context_summary = build_context_summary(ctx)
    parsed = await parse_user_message(text, context_summary)

    logger.info(
        f"[HANDLE] parsed: intent={parsed.intent} confidence={parsed.confidence:.2f} "
        f"entities={parsed.entities} fallback={parsed.used_fallback} "
        f"context_used={has_context}"
    )

    # ── 6. Confidence-based routing ──────────────────────
    if parsed.confidence < CONFIDENCE_MEDIUM and parsed.intent not in ("greeting", "general_chat"):
        logger.info(f"[HANDLE] Low confidence ({parsed.confidence:.2f}) — asking clarification")
        return (
            "🤔 Tu veux :\n"
            "• Ajouter une dépense ? (ex: \"25 resto\")\n"
            "• Un avis achat ? (ex: \"iPhone à 1200€\")\n"
            "• Voir ton résumé ? → /summary\n"
            "• Annuler ? → \"annule\""
        )

    # ── 7. Route to handler based on intent ──────────────
    response = await _route_intent(db, user, text, parsed, ctx)

    # ── 8. Save context and response to history ──────────
    await update_context(
        db, user.id,
        last_intent=parsed.intent,
        last_topic=parsed.intent,
    )
    await add_message_to_history(db, user.id, "assistant", response)

    logger.info(f"[HANDLE] response sent ({len(response)} chars)")
    return response


async def _route_intent(
    db: AsyncSession,
    user: User,
    text: str,
    parsed: ParsedMessage,
    ctx,
) -> str:
    """Route to the appropriate handler based on parsed intent."""
    intent = parsed.intent
    entities = parsed.entities

    if intent == "add_expense":
        return await _handle_add_transaction(db, user, entities, is_income=False)

    elif intent == "add_income":
        return await _handle_add_transaction(db, user, entities, is_income=True)

    elif intent == "add_multiple":
        return await _handle_add_multiple(db, user, entities)

    elif intent == "ask_purchase":
        return await _handle_purchase_decision(db, user, text, entities, ctx)

    elif intent == "show_summary":
        return await _handle_summary(db, user)

    elif intent == "correct_last":
        return await _handle_correct_last(db, user, entities)

    elif intent == "cancel_last":
        return await _handle_cancel_last(db, user)

    elif intent == "update_profile":
        return "Pour modifier ton profil, utilise /profile ✏️"

    elif intent == "greeting":
        profile = await profile_service.get_or_create_profile(db, user.id)
        fin_summary = f"Revenu: {profile.monthly_income}€, Épargne: {profile.available_savings}€"
        return await generate_conversational_response(
            intent="greeting",
            user_message=text,
            context_summary=build_context_summary(ctx),
            financial_summary=fin_summary,
        )

    elif intent == "general_chat":
        profile = await profile_service.get_or_create_profile(db, user.id)
        fin_summary = (
            f"Revenu: {profile.monthly_income}€, "
            f"Charges: {profile.monthly_fixed_charges}€, "
            f"Épargne: {profile.available_savings}€"
        )
        return await generate_conversational_response(
            intent="general_chat",
            user_message=text,
            context_summary=build_context_summary(ctx),
            financial_summary=fin_summary,
        )

    else:
        return await generate_conversational_response(
            intent="unknown",
            user_message=text,
            context_summary=build_context_summary(ctx),
        )


# ── Duplicate Detection ──────────────────────────────────

async def _is_duplicate_message(ctx, text: str) -> bool:
    """Detect Telegram retry duplicates by checking last user message."""
    messages = ctx.recent_messages or []
    if not messages:
        return False
    # Check if last message is identical and from user
    last = messages[-1]
    if last.get("role") == "user" and last.get("content", "").strip() == text.strip():
        return True
    return False


# ── Transaction Handlers ─────────────────────────────────

def _safe_decimal(value) -> Decimal | None:
    """Safely convert a value to Decimal, returning None on failure."""
    if value is None:
        return None
    try:
        d = Decimal(str(value))
        return d if d > 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


async def _handle_add_transaction(
    db: AsyncSession,
    user: User,
    entities: dict,
    is_income: bool,
) -> str:
    """Record a single transaction from AI-parsed entities."""
    amount = _safe_decimal(entities.get("amount"))
    if not amount:
        return "❌ Je n'ai pas trouvé de montant. Essaie : \"25 resto\" ou \"j'ai reçu 1200\""

    category_str = entities.get("category", "autre")
    description = entities.get("description", category_str)

    try:
        category = TransactionCategory(category_str)
    except ValueError:
        category = TransactionCategory.AUTRE

    tx_type = TransactionType.INCOME if is_income else TransactionType.EXPENSE

    tx_data = TransactionCreate(
        amount=amount,
        category=category,
        description=description,
        transaction_type=tx_type,
    )
    await transaction_service.create_transaction(db, user.id, tx_data)

    await update_context(
        db, user.id,
        last_amount=str(amount),
        last_topic="transaction",
    )

    emoji = "📥" if is_income else "📤"
    logger.info(f"[TX] Recorded {tx_type.value}: {amount}€ {category_str} for user {user.id}")
    return (
        f"{emoji} *{float(amount):.2f}€* — {category_str}\n"
        f"_{description}_\n"
        f"✅ Enregistré !"
    )


async def _handle_add_multiple(
    db: AsyncSession,
    user: User,
    entities: dict,
) -> str:
    """Record multiple transactions from a single message."""
    items = entities.get("items", [])
    if not items:
        return "❌ Je n'ai pas trouvé de dépenses. Essaie : \"loyer 500 + transport 50\""

    results = []
    total = Decimal("0")
    for item in items:
        amount = _safe_decimal(item.get("amount"))
        if not amount:
            continue

        category_str = item.get("category", "autre")
        description = item.get("description", category_str)
        is_income = item.get("type", "expense") == "income"

        try:
            category = TransactionCategory(category_str)
        except ValueError:
            category = TransactionCategory.AUTRE

        tx_type = TransactionType.INCOME if is_income else TransactionType.EXPENSE
        tx_data = TransactionCreate(
            amount=amount,
            category=category,
            description=description,
            transaction_type=tx_type,
        )
        await transaction_service.create_transaction(db, user.id, tx_data)

        emoji = "📥" if is_income else "📤"
        results.append(f"{emoji} {float(amount):.2f}€ — {category_str}")
        total += amount

    if not results:
        return "❌ Aucune transaction valide trouvée."

    lines = "\n".join(results)
    logger.info(f"[TX] Recorded {len(results)} transactions, total={total}€ for user {user.id}")
    return f"✅ *{len(results)} transactions enregistrées :*\n\n{lines}\n\n💰 Total : {float(total):.2f}€"


# ── Correction & Cancel Handlers ─────────────────────────

async def _handle_correct_last(
    db: AsyncSession, user: User, entities: dict
) -> str:
    """Correct the last transaction amount."""
    new_amount = _safe_decimal(entities.get("amount"))
    if not new_amount:
        return "❌ Quel est le bon montant ? (ex: \"corrige 20\")"

    last_tx = await transaction_service.get_last_transaction(db, user.id)
    if not last_tx:
        return "🤷 Aucune transaction récente à corriger."

    old_amount = last_tx.amount
    updated = await transaction_service.update_transaction_amount(db, last_tx.id, new_amount)
    if updated:
        logger.info(f"[CORRECT] user={user.id} tx={last_tx.id}: {old_amount}€ → {new_amount}€")
        return (
            f"✏️ Corrigé !\n"
            f"• Avant : {float(old_amount):.2f}€\n"
            f"• Maintenant : {float(new_amount):.2f}€"
        )
    return "❌ Impossible de corriger cette transaction."


async def _handle_cancel_last(db: AsyncSession, user: User) -> str:
    """Cancel (delete) the last transaction."""
    last_tx = await transaction_service.get_last_transaction(db, user.id)
    if not last_tx:
        return "🤷 Aucune transaction récente à annuler."

    amount = last_tx.amount
    category = last_tx.category
    deleted = await transaction_service.delete_transaction(db, last_tx.id)
    if deleted:
        logger.info(f"[CANCEL] user={user.id} deleted tx: {amount}€ {category}")
        return f"🗑️ Supprimé : {float(amount):.2f}€ — {category}"
    return "❌ Impossible d'annuler cette transaction."


# ── Purchase Decision Handler ────────────────────────────

async def _handle_purchase_decision(
    db: AsyncSession,
    user: User,
    text: str,
    entities: dict,
    ctx,
) -> str:
    """Evaluate a purchase decision with context awareness.

    GUARDRAIL: The financial verdict ALWAYS comes from evaluate_purchase().
    The LLM only reformulates the engine's output into natural language.
    """
    item_name = entities.get("item_name")
    price = entities.get("price")
    category = entities.get("category", "autre")

    # Context-aware: "je peux l'acheter ?" → use last discussed item
    context_used = False
    if not item_name and ctx.last_item_name:
        item_name = ctx.last_item_name
        context_used = True
        logger.info(f"[PURCHASE] Filled item from context: {item_name}")
        if not price and ctx.last_amount:
            try:
                price = float(ctx.last_amount)
                logger.info(f"[PURCHASE] Filled price from context: {price}")
            except (ValueError, TypeError):
                pass

    # Still missing item name → ask user
    if not item_name:
        await update_context(db, user.id, pending_action="need_purchase_item")
        return (
            "🛒 Qu'est-ce que tu veux acheter ?\n\n"
            "Dis-moi le nom et le prix, par exemple :\n"
            "\"iPhone à 1200€\" ou \"un vélo à 800€\""
        )

    # Missing price → ask user
    if not price:
        await update_context(
            db, user.id,
            pending_action="need_purchase_price",
            last_item_name=str(item_name),
        )
        return f"💰 Combien coûte {item_name} ?"

    price_decimal = _safe_decimal(price)
    if not price_decimal:
        return "❌ Le prix n'est pas valide. Donne-moi un montant, par exemple : \"1200€\""

    # Save item in context for follow-up
    await update_context(
        db, user.id,
        last_item_name=str(item_name),
        last_amount=str(price_decimal),
        pending_action=None,
    )

    # Build snapshot from DB data
    snapshot = await _build_financial_snapshot(db, user)
    purchase = PurchaseInput(
        item_name=str(item_name),
        price=price_decimal,
        item_category=str(category),
    )

    logger.info(
        f"[PURCHASE] Engine input: item={item_name} price={price_decimal} "
        f"income={snapshot.monthly_income} savings={snapshot.available_savings} "
        f"context_used={context_used}"
    )

    # Check for missing info
    missing = get_missing_questions(snapshot, purchase)
    if missing and snapshot.monthly_income == 0:
        questions_text = await generate_follow_up_questions(missing)
        return f"🤔 Avant de décider, j'ai besoin de quelques infos :\n\n{questions_text}"

    # GUARDRAIL: Decision comes EXCLUSIVELY from the deterministic engine
    result = evaluate_purchase(snapshot, purchase)

    logger.info(
        f"[PURCHASE] Engine output: decision={result.decision_status.value} "
        f"risk={result.risk_score} confidence={result.confidence_score}"
    )

    # Reformulate with LLM (presentation only — decision is locked)
    decision_data = result.model_dump()
    decision_data["price"] = str(price_decimal)
    decision_data["item_name"] = str(item_name)

    profile = await profile_service.get_or_create_profile(db, user.id)
    user_context = (
        f"Revenu: {profile.monthly_income}€/mois ({profile.income_type}), "
        f"Charges: {profile.monthly_fixed_charges}€, "
        f"Épargne: {profile.available_savings}€, "
        f"Dettes: {profile.total_debt}€, "
        f"Objectif: {profile.main_goal}"
    )

    response = await reformulate_decision(
        decision_data,
        user_context=user_context,
    )
    return response


# ── Pending Action Handler ────────────────────────────────

async def _handle_pending_action(
    db: AsyncSession,
    user: User,
    text: str,
    ctx,
) -> str | None:
    """Handle continuation of a multi-turn flow."""
    action = ctx.pending_action

    if action == "need_purchase_item":
        parsed = await parse_user_message(text, build_context_summary(ctx))
        entities = parsed.entities
        item_name = entities.get("item_name") or text.strip()
        price = entities.get("price")

        await clear_pending_action(db, user.id)
        return await _handle_purchase_decision(
            db, user, text,
            {"item_name": item_name, "price": price, "category": entities.get("category", "autre")},
            ctx,
        )

    elif action == "need_purchase_price":
        from app.services.llm_service import parse_natural_amount
        price = await parse_natural_amount(text)
        if price is None or price <= 0:
            return "❌ Je n'ai pas compris le prix. Donne-moi juste le montant, par exemple : \"1200\" ou \"1200€\""

        await clear_pending_action(db, user.id)
        return await _handle_purchase_decision(
            db, user, text,
            {"item_name": ctx.last_item_name, "price": price, "category": "autre"},
            ctx,
        )

    elif action == "guided_expense_amount":
        # User gave an amount after clicking a category button
        from app.services.llm_service import parse_natural_amount
        amount = await parse_natural_amount(text)
        if amount is None or amount <= 0:
            return "❌ Je n'ai pas compris le montant. Combien ?"

        extra = ctx.context_data or {}
        category = extra.get("guided_category", "autre")
        await clear_pending_action(db, user.id)
        return await _handle_add_transaction(
            db, user,
            {"amount": amount, "category": category, "description": category},
            is_income=False,
        )

    elif action == "guided_expense_category":
        # User typed a category instead of clicking a button
        parsed = await parse_user_message(text, build_context_summary(ctx))
        if parsed.intent in ("add_expense", "add_income", "add_multiple"):
            await clear_pending_action(db, user.id)
            return await _route_intent(db, user, text, parsed, ctx)
        return "📂 Clique sur une catégorie ci-dessus, ou tape directement ta dépense (ex: \"25 resto\")"

    logger.warning(f"[HANDLE] Unknown pending action: {action}")
    await clear_pending_action(db, user.id)
    return None


# ── Onboarding Handler ───────────────────────────────────

async def _handle_onboarding(
    db: AsyncSession, user: User, text: str, ctx
) -> str:
    """Handle onboarding step by step with DB-backed state and AI parsing."""
    from app.services.llm_service import parse_natural_amount, parse_natural_choice

    current_step = ctx.onboarding_step or OnboardingStep.WELCOME

    if current_step == OnboardingStep.WELCOME:
        await update_context(db, user.id, onboarding_step=OnboardingStep.MONTHLY_INCOME)
        return ONBOARDING_QUESTIONS[OnboardingStep.WELCOME]

    profile = await profile_service.get_or_create_profile(db, user.id)

    try:
        step = OnboardingStep(current_step)
    except ValueError:
        step = OnboardingStep.MONTHLY_INCOME

    logger.info(f"[ONBOARD] step={step.value} answer={text!r} user={user.telegram_id}")

    if step == OnboardingStep.MONTHLY_INCOME:
        amount = await parse_natural_amount(text)
        if amount is None:
            return "💰 Je n'ai pas compris le montant. Quel est ton revenu mensuel net en euros ?"
        await profile_service.update_profile_field(db, user.id, "monthly_income", Decimal(str(amount)))
        next_step = OnboardingStep.INCOME_TYPE

    elif step == OnboardingStep.INCOME_TYPE:
        income_type = await parse_natural_choice(text, {
            "stable": ["stable", "cdi", "fonctionnaire", "permanent", "fixe"],
            "variable": ["variable", "commission", "prime", "primes"],
            "internship": ["stage", "cdd", "stagiaire", "temporaire", "intérim", "interim"],
            "freelance": ["freelance", "indépendant", "independant", "auto-entrepreneur", "micro"],
            "none": ["sans", "aucun", "pas de", "chômage", "chomage", "0"],
        }, default="stable")
        await profile_service.update_profile_field(db, user.id, "income_type", income_type)
        if should_ask_income_end_date(income_type):
            next_step = OnboardingStep.INCOME_END_DATE
        else:
            next_step = OnboardingStep.MONTHLY_CHARGES

    elif step == OnboardingStep.INCOME_END_DATE:
        await profile_service.update_profile_field(db, user.id, "income_end_date", text.strip())
        next_step = OnboardingStep.MONTHLY_CHARGES

    elif step == OnboardingStep.MONTHLY_CHARGES:
        amount = await parse_natural_amount(text)
        if amount is None:
            return "🏠 Je n'ai pas compris. Quel est le montant total de tes charges fixes mensuelles ?"
        await profile_service.update_profile_field(db, user.id, "monthly_fixed_charges", Decimal(str(amount)))
        next_step = OnboardingStep.AVAILABLE_SAVINGS

    elif step == OnboardingStep.AVAILABLE_SAVINGS:
        amount = await parse_natural_amount(text)
        if amount is None:
            return "🏦 Je n'ai pas compris. Combien d'épargne as-tu au total ?"
        await profile_service.update_profile_field(db, user.id, "available_savings", Decimal(str(amount)))
        next_step = OnboardingStep.TOTAL_DEBT

    elif step == OnboardingStep.TOTAL_DEBT:
        amount = await parse_natural_amount(text)
        if amount is None:
            return "💳 Je n'ai pas compris. As-tu des dettes ? Si oui combien, sinon dis juste 0."
        await profile_service.update_profile_field(db, user.id, "total_debt", Decimal(str(amount)))
        next_step = OnboardingStep.HOUSING_SITUATION

    elif step == OnboardingStep.HOUSING_SITUATION:
        housing = await parse_natural_choice(text, {
            "alone": ["seul", "seule", "studio", "solo", "appartement"],
            "family": ["famille", "parents", "maison", "chez mes parents"],
            "shared": ["colocation", "coloc", "colocataire", "partagé", "partage"],
        }, default="alone")
        await profile_service.update_profile_field(db, user.id, "housing_situation", housing)
        next_step = OnboardingStep.SAFETY_NET_MONTHS

    elif step == OnboardingStep.SAFETY_NET_MONTHS:
        amount = await parse_natural_amount(text)
        months = int(amount) if amount is not None and amount > 0 else 3
        mapping = {"1": 1, "2": 3, "3": 6}
        if text.strip() in mapping:
            months = mapping[text.strip()]
        await profile_service.update_profile_field(db, user.id, "safety_net_months", months)
        next_step = OnboardingStep.MAIN_GOAL

    elif step == OnboardingStep.MAIN_GOAL:
        goal = await parse_natural_choice(text, {
            "stability": ["stabilité", "stabilite", "stable", "sécurité", "securite"],
            "car": ["voiture", "auto", "car", "véhicule", "vehicule"],
            "travel": ["voyage", "vacances", "voyager"],
            "investment": ["investissement", "investir", "bourse", "immobilier"],
            "pay_debt": ["dette", "rembourser", "crédit", "credit"],
            "other": ["autre", "autre chose"],
        }, default="other")
        button_map = {"1": "stability", "2": "car", "3": "travel", "4": "investment", "5": "pay_debt", "6": "other"}
        if text.strip() in button_map:
            goal = button_map[text.strip()]
        await profile_service.update_profile_field(db, user.id, "main_goal", goal)
        next_step = OnboardingStep.RISK_TOLERANCE

    elif step == OnboardingStep.RISK_TOLERANCE:
        risk = await parse_natural_choice(text, {
            "prudent": ["prudent", "prudente", "sécurité", "securite", "safe"],
            "balanced": ["équilibré", "equilibre", "équilibre", "modéré", "modere", "mix"],
            "aggressive": ["agressif", "agressive", "croissance", "risque", "bold"],
        }, default="balanced")
        button_map = {"1": "prudent", "2": "balanced", "3": "aggressive"}
        if text.strip() in button_map:
            risk = button_map[text.strip()]
        await profile_service.update_profile_field(db, user.id, "risk_tolerance", risk)
        await profile_service.mark_onboarding_complete(db, user.id)
        await update_context(db, user.id, onboarding_step=None, pending_action=None)
        logger.info(f"[ONBOARD] Completed for user {user.telegram_id}")
        return ONBOARDING_QUESTIONS[OnboardingStep.COMPLETED]

    else:
        next_step = OnboardingStep.MONTHLY_INCOME

    await update_context(db, user.id, onboarding_step=next_step.value)
    return ONBOARDING_QUESTIONS.get(next_step, "❓")


# ── Summary Handler ───────────────────────────────────────

async def _handle_summary(db: AsyncSession, user: User) -> str:
    """Generate and return financial summary from actual DB data."""
    summary = await reporting_service.get_financial_summary(db, user)
    return reporting_service.format_summary_message(summary)


# ── Financial Snapshot Builder ───────────────────────────

async def _build_financial_snapshot(
    db: AsyncSession, user: User
) -> UserFinancialSnapshot:
    """Build a complete financial snapshot for the decision engine.

    Sources data from:
    - FinancialProfile (onboarding data)
    - Accounts (actual balances when available)
    - Transactions (tracked spending)

    When no accounts exist, falls back to profile.available_savings.
    """
    profile = await profile_service.get_or_create_profile(db, user.id)
    total_liquid = await account_service.get_total_liquid_cash(db, user.id)
    total_patrimony = await account_service.get_total_patrimony(db, user.id)
    monthly_spending = await transaction_service.get_monthly_spending(db, user.id)
    spending_trend = await transaction_service.get_spending_trend(db, user.id)
    top_categories = await transaction_service.get_spending_by_category(db, user.id)

    effective_liquid = total_liquid if total_liquid > 0 else profile.available_savings
    effective_patrimony = total_patrimony if total_patrimony > 0 else profile.available_savings

    from app.db.models.goal import Goal
    from sqlalchemy import select
    result = await db.execute(
        select(Goal).where(Goal.user_id == user.id).where(Goal.is_active.is_(True))
    )
    goals = result.scalars().all()
    active_goals = [
        {"name": g.name, "remaining": str(g.remaining), "deadline_months": g.deadline_months}
        for g in goals
    ]

    snapshot = UserFinancialSnapshot(
        monthly_income=profile.monthly_income,
        income_type=profile.income_type,
        income_end_date=getattr(profile, 'income_end_date', None),
        monthly_fixed_charges=profile.monthly_fixed_charges,
        available_savings=profile.available_savings,
        total_debt=profile.total_debt,
        safety_net_months=profile.safety_net_months,
        main_goal=profile.main_goal,
        risk_tolerance=profile.risk_tolerance,
        total_liquid_cash=effective_liquid,
        total_patrimony=effective_patrimony,
        monthly_spending_avg=monthly_spending,
        spending_trend=spending_trend,
        top_spending_categories=[
            {"category": c["category"], "total": str(c["total"])}
            for c in top_categories
        ],
        active_goals=active_goals,
    )

    logger.debug(
        f"[SNAPSHOT] user={user.id} income={profile.monthly_income} "
        f"liquid={effective_liquid} spending={monthly_spending}"
    )
    return snapshot
