"""Telegram webhook endpoint — handles messages, commands, and button callbacks."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.services.profile_service import get_or_create_user
from app.services.telegram_service import handle_message
from app.services.telegram_buttons import (
    main_menu_keyboard,
    expense_category_keyboard,
    parse_callback_data,
)

logger = get_logger("webhook")

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(None),
):
    """Handle incoming Telegram updates — messages and callback queries."""
    from app.core.security import verify_telegram_secret

    if x_telegram_bot_api_secret_token:
        if not verify_telegram_secret(x_telegram_bot_api_secret_token):
            raise HTTPException(status_code=403, detail="Invalid secret")

    body = await request.json()
    logger.info(f"Webhook update_id={body.get('update_id', '?')}")

    # ── Handle callback queries (button clicks) ──────────
    callback_query = body.get("callback_query")
    if callback_query:
        await _handle_callback_query(db, callback_query)
        return {"ok": True}

    # ── Handle messages ──────────────────────────────────
    message = body.get("message")
    if not message:
        return {"ok": True}

    text = message.get("text", "")
    if not text:
        return {"ok": True}

    from_user = message.get("from", {})
    telegram_id = from_user.get("id")
    chat_id = message.get("chat", {}).get("id")

    if not telegram_id or not chat_id:
        return {"ok": True}

    user = await get_or_create_user(
        db,
        telegram_id=telegram_id,
        username=from_user.get("username"),
        first_name=from_user.get("first_name"),
        last_name=from_user.get("last_name"),
    )

    try:
        if text.startswith("/"):
            result = await _handle_command(db, user, text, chat_id)
        else:
            response_text = await handle_message(db, user, text)
            result = {"text": response_text}

        await db.commit()
    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        await db.rollback()
        result = {"text": "⚠️ Oups, une erreur est survenue. Réessaie dans un instant !"}

    # Send response — with optional buttons
    await _send_telegram_message(
        chat_id,
        result.get("text", ""),
        reply_markup=result.get("reply_markup"),
    )
    return {"ok": True}


# ── Callback Query Handler ───────────────────────────────

async def _handle_callback_query(db: AsyncSession, callback_query: dict):
    """Handle InlineKeyboard button clicks."""
    callback_id = callback_query.get("id")
    data = callback_query.get("data", "")
    from_user = callback_query.get("from", {})
    telegram_id = from_user.get("id")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")

    if not telegram_id or not chat_id:
        return

    logger.info(f"[CALLBACK] user={telegram_id} data={data!r}")

    # Acknowledge the callback (removes loading spinner)
    await _answer_callback_query(callback_id)

    user = await get_or_create_user(
        db, telegram_id=telegram_id,
        username=from_user.get("username"),
        first_name=from_user.get("first_name"),
    )

    try:
        result = await _route_callback(db, user, data)
        await db.commit()
    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        await db.rollback()
        result = {"text": "⚠️ Erreur, réessaie."}

    await _send_telegram_message(
        chat_id,
        result.get("text", ""),
        reply_markup=result.get("reply_markup"),
    )


async def _route_callback(db, user, data: str) -> dict:
    """Route callback_data to the appropriate handler."""
    from app.services.telegram_service import _handle_summary
    from app.services.context_service import update_context

    prefix, value = parse_callback_data(data)

    # ── Main menu buttons ────────────────────────────────
    if data == "menu_add_expense":
        await update_context(db, user.id, pending_action="guided_expense_category")
        return {
            "text": "📂 Quel type de dépense ?",
            "reply_markup": expense_category_keyboard(),
        }

    if data == "menu_summary":
        text = await _handle_summary(db, user)
        return {"text": text}

    if data == "menu_canibuy":
        await update_context(db, user.id, pending_action="need_purchase_item")
        return {
            "text": (
                "🛒 Qu'est-ce que tu veux acheter ?\n\n"
                "Dis-moi le nom et le prix, par exemple :\n"
                "\"iPhone à 1200€\" ou \"un vélo à 800€\""
            ),
        }

    if data == "menu_profile":
        from app.services.profile_service import get_or_create_profile
        profile = await get_or_create_profile(db, user.id)
        return {
            "text": (
                f"👤 *Ton profil financier*\n\n"
                f"💰 Revenu : {profile.monthly_income}€/mois ({profile.income_type})\n"
                f"🏠 Charges : {profile.monthly_fixed_charges}€/mois\n"
                f"🏦 Épargne : {profile.available_savings}€\n"
                f"💳 Dettes : {profile.total_debt}€\n"
                f"🎯 Objectif : {profile.main_goal}\n"
                f"⚖️ Risque : {profile.risk_tolerance}"
            ),
        }

    if data == "menu_help":
        return {
            "text": (
                "🤖 *CashPilot — Aide*\n\n"
                "Tu peux parler naturellement :\n"
                "• \"25 resto\" → ajoute une dépense\n"
                "• \"loyer 500 + transport 50\" → multi-dépenses\n"
                "• \"je peux acheter un iPhone à 1200€ ?\" → avis achat\n"
                "• \"annule\" → annuler la dernière opération\n"
                "• \"corrige 20\" → corriger le dernier montant\n\n"
                "📊 /summary — Résumé financier\n"
                "🛒 /canibuy — Avis achat\n"
                "👤 /profile — Ton profil"
            ),
        }

    # ── Category picker buttons ──────────────────────────
    if prefix == "cat":
        category = value  # e.g., "restaurant", "transport"
        await update_context(
            db, user.id,
            pending_action="guided_expense_amount",
            extra_data={"guided_category": category},
        )
        emoji = {
            "restaurant": "🍔", "transport": "🚗", "logement": "🏠",
            "alimentation": "🛒", "loisir": "🎉", "abonnement": "📱",
            "shopping": "🛍️", "santé": "💊", "autre": "📦",
        }.get(category, "📦")
        return {"text": f"{emoji} Combien as-tu dépensé en *{category}* ?"}

    # ── Confirmation buttons ─────────────────────────────
    if data.startswith("confirm_yes"):
        from app.services.context_service import get_context, clear_pending_action
        ctx = await get_context(db, user.id)
        pending = ctx.context_data or {}
        if "confirm_text" in pending:
            # Re-process the confirmed message
            text = pending.get("confirm_text", "")
            await clear_pending_action(db, user.id)
            response = await handle_message(db, user, text)
            return {"text": response}
        await clear_pending_action(db, user.id)
        return {"text": "✅ Confirmé !"}

    if data.startswith("confirm_no"):
        from app.services.context_service import clear_pending_action
        await clear_pending_action(db, user.id)
        return {"text": "❌ Annulé. Que veux-tu faire ?", "reply_markup": main_menu_keyboard()}

    if data == "action_cancel":
        from app.services.context_service import clear_pending_action
        await clear_pending_action(db, user.id)
        return {"text": "❌ Annulé.", "reply_markup": main_menu_keyboard()}

    logger.warning(f"[CALLBACK] Unknown callback data: {data!r}")
    return {"text": "🤔 Action inconnue.", "reply_markup": main_menu_keyboard()}


# ── Command Handler ──────────────────────────────────────

async def _handle_command(db, user, text: str, chat_id: int) -> dict:
    """Handle bot commands. Returns dict with text + optional reply_markup."""
    from app.services.telegram_service import _handle_summary
    from app.services.context_service import get_context, update_context
    from app.services.onboarding_service import OnboardingStep, ONBOARDING_QUESTIONS

    cmd = text.split()[0].lower().replace("@", "").split("@")[0]

    if cmd == "/start":
        if not user.onboarding_completed:
            await get_context(db, user.id)
            await update_context(db, user.id, onboarding_step=OnboardingStep.WELCOME)
            return {"text": ONBOARDING_QUESTIONS[OnboardingStep.WELCOME]}
        return {
            "text": (
                "👋 Salut ! Je suis *CashPilot*, ton copilote financier 🚀\n\n"
                "Que veux-tu faire ?"
            ),
            "reply_markup": main_menu_keyboard(),
        }

    if cmd == "/help":
        return {
            "text": (
                "🤖 *CashPilot — Aide*\n\n"
                "💡 Parle-moi naturellement :\n"
                "\"25 resto\", \"loyer 500 + transport 50\",\n"
                "\"je peux acheter un iPhone à 1200€ ?\"\n\n"
                "📊 /summary — Résumé financier\n"
                "💳 /accounts — Tes comptes\n"
                "🎯 /goals — Tes objectifs\n"
                "🛒 /canibuy — Avis achat\n"
                "👤 /profile — Ton profil\n"
                "❤️ /health — Santé financière"
            ),
        }

    if cmd == "/summary":
        text = await _handle_summary(db, user)
        return {"text": text}

    if cmd == "/menu":
        return {
            "text": "📋 Menu principal",
            "reply_markup": main_menu_keyboard(),
        }

    if cmd == "/accounts":
        from app.services import account_service
        accounts = await account_service.get_user_accounts(db, user.id)
        if not accounts:
            return {"text": "💳 Aucun compte enregistré. Utilise /add\\_account pour en ajouter un."}
        lines = ["💳 *Tes comptes :*\n"]
        for a in accounts:
            emoji = {"bank": "🏦", "savings": "💰", "cash": "💵", "crypto": "🪙"}.get(a.account_type, "💳")
            lines.append(f"{emoji} {a.name} ({a.account_type}) : {a.balance}€")
        total = sum(a.balance for a in accounts)
        lines.append(f"\n💰 Total : {total}€")
        return {"text": "\n".join(lines)}

    if cmd == "/add_account":
        return {
            "text": (
                "➕ Pour ajouter un compte, envoie :\n"
                "`nom_du_compte type solde`\n\n"
                "Exemple : `Boursorama bank 2500`\n\n"
                "Types : bank, neo_bank, savings, cash, crypto, paypal, meal_voucher, investment, other"
            ),
        }

    if cmd == "/goals":
        from sqlalchemy import select
        from app.db.models.goal import Goal
        result = await db.execute(
            select(Goal).where(Goal.user_id == user.id).where(Goal.is_active.is_(True))
        )
        goals = list(result.scalars().all())
        if not goals:
            return {"text": "🎯 Aucun objectif défini. Bientôt tu pourras en créer !"}
        lines = ["🎯 *Tes objectifs :*\n"]
        for g in goals:
            pct = g.progress_pct
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            lines.append(f"• {g.name}: {g.current_amount}/{g.target_amount}€\n  [{bar}] {pct:.0f}%")
        return {"text": "\n".join(lines)}

    if cmd == "/canibuy":
        return {
            "text": (
                "🛒 Dis-moi ce que tu veux acheter !\n\n"
                "Tu peux écrire naturellement :\n"
                "\"Est-ce que je peux acheter un iPhone à 1200€ ?\"\n"
                "\"Je veux acheter une voiture à 5000€\"\n"
                "\"Un MacBook à 2500, c'est raisonnable ?\""
            ),
        }

    if cmd == "/profile":
        from app.services.profile_service import get_or_create_profile
        profile = await get_or_create_profile(db, user.id)
        return {
            "text": (
                f"👤 *Ton profil financier*\n\n"
                f"💰 Revenu : {profile.monthly_income}€/mois ({profile.income_type})\n"
                f"🏠 Charges : {profile.monthly_fixed_charges}€/mois\n"
                f"🏦 Épargne : {profile.available_savings}€\n"
                f"💳 Dettes : {profile.total_debt}€\n"
                f"🛡️ Matelas cible : {profile.safety_net_months} mois\n"
                f"🎯 Objectif : {profile.main_goal}\n"
                f"⚖️ Risque : {profile.risk_tolerance}"
            ),
        }

    if cmd == "/health":
        from app.services import reporting_service
        summary = await reporting_service.get_financial_summary(db, user)
        health = summary["health_status"]
        emoji = {"fragile": "🔴", "correct": "🟡", "solide": "🟢"}.get(health, "⚪")
        return {"text": f"{emoji} Santé financière : *{health.upper()}*"}

    return {"text": "❓ Commande inconnue. Tape /help pour voir les commandes."}


# ── Telegram API Helpers ─────────────────────────────────

async def _send_telegram_message(
    chat_id: int,
    text: str,
    reply_markup: dict | None = None,
) -> None:
    """Send a message via the Telegram Bot API, optionally with buttons."""
    import httpx
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("No TELEGRAM_BOT_TOKEN — skipping message send")
        return

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload: dict = {
        "chat_id": chat_id,
        "text": text or "...",
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram send failed: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"Telegram send error: {e}")


async def _answer_callback_query(callback_id: str, text: str = "") -> None:
    """Acknowledge a callback query (removes the loading spinner on the button)."""
    import httpx
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        return

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    payload: dict = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=payload)
    except Exception as e:
        logger.error(f"answerCallbackQuery error: {e}")
