"""Inline and reply keyboards for structured user input."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


def income_type_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["1️⃣ Stable (CDI)", "2️⃣ Variable"],
            ["3️⃣ Stage / CDD", "4️⃣ Freelance"],
            ["5️⃣ Sans revenu"],
        ],
        one_time_keyboard=True,
        resize_keyboard=True,
    )


def housing_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["1️⃣ Seul(e)", "2️⃣ En famille", "3️⃣ En colocation"]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )


def safety_net_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["1️⃣ 1 mois", "2️⃣ 3 mois", "3️⃣ 6 mois"]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )


def main_goal_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["1️⃣ Stabilité", "2️⃣ Voiture"],
            ["3️⃣ Voyage", "4️⃣ Investissement"],
            ["5️⃣ Rembourser dette", "6️⃣ Autre"],
        ],
        one_time_keyboard=True,
        resize_keyboard=True,
    )


def risk_tolerance_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["1️⃣ Prudent", "2️⃣ Équilibré", "3️⃣ Agressif"]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )


def essentiality_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔴 Essentiel", callback_data="essential"),
                InlineKeyboardButton("🟡 Utile", callback_data="useful"),
            ],
            [
                InlineKeyboardButton("🟢 Confort", callback_data="comfort"),
                InlineKeyboardButton("⚪ Impulsif", callback_data="impulse"),
            ],
        ]
    )


def account_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏦 Banque", callback_data="bank"),
                InlineKeyboardButton("📱 Néo-banque", callback_data="neo_bank"),
            ],
            [
                InlineKeyboardButton("💰 Épargne", callback_data="savings"),
                InlineKeyboardButton("💵 Cash", callback_data="cash"),
            ],
            [
                InlineKeyboardButton("🪙 Crypto", callback_data="crypto"),
                InlineKeyboardButton("🅿️ PayPal", callback_data="paypal"),
            ],
            [
                InlineKeyboardButton("🍽️ Titres resto", callback_data="meal_voucher"),
                InlineKeyboardButton("📈 Investissement", callback_data="investment"),
            ],
        ]
    )
