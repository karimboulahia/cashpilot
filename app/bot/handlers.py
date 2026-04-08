"""Telegram bot handlers — alternative to webhook mode, uses polling."""

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.services.profile_service import get_or_create_user
from app.services.telegram_service import handle_message

logger = get_logger("bot.handlers")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not update.message or not update.effective_user:
        return

    async with async_session_factory() as db:
        user = await get_or_create_user(
            db,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
        )
        response = await handle_message(db, user, "/start")
        await db.commit()

    await update.message.reply_text(response, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    if not update.message:
        return
    help_text = (
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
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all free-text messages."""
    if not update.message or not update.message.text or not update.effective_user:
        return

    async with async_session_factory() as db:
        user = await get_or_create_user(
            db,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        response = await handle_message(db, user, update.message.text)
        await db.commit()

    await update.message.reply_text(response, parse_mode="Markdown")


async def generic_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all other commands by delegating to telegram_service."""
    if not update.message or not update.message.text or not update.effective_user:
        return

    async with async_session_factory() as db:
        user = await get_or_create_user(
            db,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        # Import the command handler from webhook module
        from app.api.routes.telegram_webhook import _handle_command
        response = await _handle_command(db, user, update.message.text)
        await db.commit()

    await update.message.reply_text(response, parse_mode="Markdown")


def create_bot_application() -> Application:
    """Create and configure the Telegram bot application for polling mode."""
    settings = get_settings()
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))

    # Generic handler for all other commands
    for cmd in ["summary", "accounts", "add_account", "goals", "canibuy", "profile", "health"]:
        app.add_handler(CommandHandler(cmd, generic_command_handler))

    # Free-text message handler (must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    return app
