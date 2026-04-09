"""Telegram button service — InlineKeyboard builders for CashPilot.

Provides keyboard layouts for menus, category pickers, and confirmations.
All functions return plain dicts ready for the Telegram sendMessage reply_markup.
"""

from __future__ import annotations


def main_menu_keyboard() -> dict:
    """Main menu shown after /start or when user needs guidance."""
    return {
        "inline_keyboard": [
            [
                {"text": "💰 Ajouter une dépense", "callback_data": "menu_add_expense"},
                {"text": "📊 Mon résumé", "callback_data": "menu_summary"},
            ],
            [
                {"text": "🧠 Puis-je acheter ?", "callback_data": "menu_canibuy"},
                {"text": "⚙️ Mon profil", "callback_data": "menu_profile"},
            ],
            [
                {"text": "❓ Aide", "callback_data": "menu_help"},
            ],
        ]
    }


def expense_category_keyboard() -> dict:
    """Category picker for guided expense flow."""
    return {
        "inline_keyboard": [
            [
                {"text": "🍔 Resto", "callback_data": "cat_restaurant"},
                {"text": "🚗 Transport", "callback_data": "cat_transport"},
                {"text": "🏠 Loyer", "callback_data": "cat_logement"},
            ],
            [
                {"text": "🛒 Courses", "callback_data": "cat_alimentation"},
                {"text": "🎉 Loisir", "callback_data": "cat_loisir"},
                {"text": "📱 Abo", "callback_data": "cat_abonnement"},
            ],
            [
                {"text": "🛍️ Shopping", "callback_data": "cat_shopping"},
                {"text": "💊 Santé", "callback_data": "cat_santé"},
                {"text": "📦 Autre", "callback_data": "cat_autre"},
            ],
        ]
    }


def confirmation_keyboard(action_id: str = "confirm") -> dict:
    """Yes/No confirmation for medium-confidence actions."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Oui", "callback_data": f"confirm_yes_{action_id}"},
                {"text": "❌ Non", "callback_data": f"confirm_no_{action_id}"},
            ]
        ]
    }


def cancel_keyboard() -> dict:
    """Simple cancel button."""
    return {
        "inline_keyboard": [
            [{"text": "❌ Annuler", "callback_data": "action_cancel"}],
        ]
    }


# ── Callback data parsing ────────────────────────────────

def parse_callback_data(data: str) -> tuple[str, str]:
    """Parse callback_data into (action, value).

    Examples:
        "menu_add_expense" → ("menu", "add_expense")
        "cat_restaurant"   → ("cat", "restaurant")
        "confirm_yes_tx"   → ("confirm_yes", "tx")
        "action_cancel"    → ("action", "cancel")
    """
    parts = data.split("_", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return data, ""
