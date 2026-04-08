"""Telegram webhook endpoint."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import verify_telegram_secret
from app.db.session import get_db
from app.services.profile_service import get_or_create_user
from app.services.telegram_service import handle_message

logger = get_logger("webhook")

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(None),
):
    """Handle incoming Telegram updates via webhook."""
    # Verify secret
    if x_telegram_bot_api_secret_token:
        if not verify_telegram_secret(x_telegram_bot_api_secret_token):
            raise HTTPException(status_code=403, detail="Invalid secret")

    body = await request.json()
    logger.info(f"Webhook received: {body.get('update_id', 'unknown')}")

    # Extract message
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

    # Get or create user
    user = await get_or_create_user(
        db,
        telegram_id=telegram_id,
        username=from_user.get("username"),
        first_name=from_user.get("first_name"),
        last_name=from_user.get("last_name"),
    )

    # Handle commands
    if text.startswith("/"):
        response_text = await _handle_command(db, user, text)
    else:
        response_text = await handle_message(db, user, text)

    # Send response via Telegram API
    await _send_telegram_message(chat_id, response_text)

    return {"ok": True}


async def _handle_command(db, user, text: str) -> str:
    """Handle bot commands."""
    from app.services.telegram_service import _handle_summary, _onboarding_state
    from app.services.onboarding_service import OnboardingStep, ONBOARDING_QUESTIONS

    cmd = text.split()[0].lower().replace("@", "").split("@")[0]

    if cmd == "/start":
        if not user.onboarding_completed:
            _onboarding_state[user.telegram_id] = OnboardingStep.WELCOME
            return ONBOARDING_QUESTIONS[OnboardingStep.WELCOME]
        return (
            "👋 Re-bonjour ! Tu peux :\n"
            "• Noter une dépense : \"25 resto\"\n"
            "• Demander un avis : /canibuy\n"
            "• Voir ton résumé : /summary\n"
            "• Voir tes comptes : /accounts"
        )

    if cmd == "/help":
        return (
            "🤖 *CashPilot — Aide*\n\n"
            "📊 /summary — Résumé financier\n"
            "💳 /accounts — Tes comptes\n"
            "➕ /add\\_account — Ajouter un compte\n"
            "🎯 /goals — Tes objectifs\n"
            "🛒 /canibuy — Est-ce que je peux acheter ?\n"
            "👤 /profile — Ton profil\n"
            "❤️ /health — Santé financière\n\n"
            "💡 Tu peux aussi juste m'envoyer tes dépenses :\n"
            "\"25 resto\", \"18 uber\", \"120 loyer\""
        )

    if cmd == "/summary":
        return await _handle_summary(db, user)

    if cmd == "/accounts":
        from app.services import account_service
        accounts = await account_service.get_user_accounts(db, user.id)
        if not accounts:
            return "💳 Aucun compte enregistré. Utilise /add\\_account pour en ajouter un."
        lines = ["💳 *Tes comptes :*\n"]
        for a in accounts:
            emoji = {"bank": "🏦", "savings": "💰", "cash": "💵", "crypto": "🪙"}.get(
                a.account_type, "💳"
            )
            lines.append(f"{emoji} {a.name} ({a.account_type}) : {a.balance}€")
        total = sum(a.balance for a in accounts)
        lines.append(f"\n💰 Total : {total}€")
        return "\n".join(lines)

    if cmd == "/add_account":
        return (
            "➕ Pour ajouter un compte, envoie :\n"
            "`nom_du_compte type solde`\n\n"
            "Exemple : `Boursorama bank 2500`\n\n"
            "Types : bank, neo_bank, savings, cash, crypto, paypal, meal_voucher, investment, other"
        )

    if cmd == "/goals":
        from sqlalchemy import select
        from app.db.models.goal import Goal
        result = await db.execute(
            select(Goal).where(Goal.user_id == user.id).where(Goal.is_active.is_(True))
        )
        goals = list(result.scalars().all())
        if not goals:
            return "🎯 Aucun objectif défini. Bientôt tu pourras en créer !"
        lines = ["🎯 *Tes objectifs :*\n"]
        for g in goals:
            pct = g.progress_pct
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            lines.append(f"• {g.name}: {g.current_amount}/{g.target_amount}€\n  [{bar}] {pct:.0f}%")
        return "\n".join(lines)

    if cmd == "/canibuy":
        return (
            "🛒 Dis-moi ce que tu veux acheter !\n\n"
            "Exemple :\n"
            "\"Est-ce que je peux acheter un iPhone à 1200€ ?\"\n"
            "\"Je veux acheter une voiture à 5000€\""
        )

    if cmd == "/profile":
        from app.services.profile_service import get_or_create_profile
        profile = await get_or_create_profile(db, user.id)
        return (
            f"👤 *Ton profil financier*\n\n"
            f"💰 Revenu : {profile.monthly_income}€/mois ({profile.income_type})\n"
            f"🏠 Charges : {profile.monthly_fixed_charges}€/mois\n"
            f"🏦 Épargne : {profile.available_savings}€\n"
            f"💳 Dettes : {profile.total_debt}€\n"
            f"🛡️ Matelas cible : {profile.safety_net_months} mois\n"
            f"🎯 Objectif : {profile.main_goal}\n"
            f"⚖️ Risque : {profile.risk_tolerance}"
        )

    if cmd == "/health":
        from app.services import reporting_service
        summary = await reporting_service.get_financial_summary(db, user)
        health = summary["health_status"]
        emoji = {"fragile": "🔴", "correct": "🟡", "solide": "🟢"}.get(health, "⚪")
        return f"{emoji} Santé financière : *{health.upper()}*"

    return "❓ Commande inconnue. Tape /help pour voir les commandes."


async def _send_telegram_message(chat_id: int, text: str) -> None:
    """Send a message via the Telegram Bot API."""
    import httpx
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("No TELEGRAM_BOT_TOKEN — skipping message send")
        return

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram send failed: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
