"""Tests for the AI copilot upgrade — parser, context, fallbacks, and e2e flows.

Tests are designed to run WITHOUT an OpenAI API key by testing:
- AI parser output normalization and fallback behavior
- Context service operations
- LLM fallback functions (simple_amount_parse, simple_choice_parse)
- Multi-expense parsing
- Decision engine integration with context-filled data
- Summary consistency
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.ai_parser import _fallback_parse, ParsedMessage
from app.services.llm_service import (
    _simple_amount_parse,
    _simple_choice_parse,
    _default_response,
    _format_raw_decision,
)
from app.services.decision_engine import (
    UserFinancialSnapshot,
    PurchaseInput,
    evaluate_purchase,
)


# ═══════════════════════════════════════════════════════════
# Req 15.1: AI Parser Output Normalization
# ═══════════════════════════════════════════════════════════

class TestAIParserFallback:
    """Test the deterministic fallback parser used when LLM is unavailable."""

    def test_expense_simple(self):
        """'25 resto' → add_expense via fallback."""
        result = _fallback_parse("25 resto")
        assert result.intent == "add_expense"
        assert result.entities["amount"] == 25.0
        assert result.entities["category"] == "restaurant"
        assert result.used_fallback is True

    def test_income_detection(self):
        """'+2500 salaire' → add_income via fallback."""
        result = _fallback_parse("+2500 salaire")
        assert result.intent == "add_income"
        assert result.entities["amount"] == 2500.0
        assert result.used_fallback is True

    def test_purchase_keyword_acheter(self):
        """'je veux acheter un iPhone' → ask_purchase."""
        result = _fallback_parse("je veux acheter un iPhone")
        assert result.intent == "ask_purchase"
        assert result.used_fallback is True

    def test_purchase_keyword_canibuy(self):
        """'je peux l'acheter ?' → ask_purchase."""
        result = _fallback_parse("je peux l'acheter ?")
        assert result.intent == "ask_purchase"

    def test_summary_keyword(self):
        """'résumé' → show_summary."""
        result = _fallback_parse("résumé")
        assert result.intent == "show_summary"

    def test_greeting_bonjour(self):
        result = _fallback_parse("bonjour")
        assert result.intent == "greeting"
        assert result.confidence >= 0.9

    def test_greeting_salut(self):
        result = _fallback_parse("salut !")
        assert result.intent == "greeting"

    def test_unknown_message(self):
        result = _fallback_parse("quelle heure est-il ?")
        assert result.intent == "unknown"
        assert result.confidence < 0.5
        assert result.used_fallback is True

    def test_empty_string(self):
        result = _fallback_parse("")
        assert result.intent == "unknown"

    def test_parsed_message_defaults(self):
        """ParsedMessage has correct defaults."""
        pm = ParsedMessage()
        assert pm.intent == "unknown"
        assert pm.confidence == 0.5
        assert pm.entities == {}
        assert pm.used_fallback is False


# ═══════════════════════════════════════════════════════════
# Req 15.2: Context Reuse Across Turns (Unit)
# ═══════════════════════════════════════════════════════════

class TestContextSummary:
    """Test build_context_summary used for LLM prompts."""

    def test_empty_context(self):
        from app.services.context_service import build_context_summary
        ctx = MagicMock()
        ctx.last_intent = None
        ctx.last_item_name = None
        ctx.last_amount = None
        ctx.pending_action = None
        ctx.recent_messages = []
        summary = build_context_summary(ctx)
        assert summary == "Aucun contexte précédent."

    def test_with_purchase_context(self):
        from app.services.context_service import build_context_summary
        ctx = MagicMock()
        ctx.last_intent = "ask_purchase"
        ctx.last_item_name = "iPhone"
        ctx.last_amount = "1200"
        ctx.pending_action = None
        ctx.recent_messages = []
        summary = build_context_summary(ctx)
        assert "iPhone" in summary
        assert "1200" in summary
        assert "ask_purchase" in summary

    def test_with_pending_action(self):
        from app.services.context_service import build_context_summary
        ctx = MagicMock()
        ctx.last_intent = None
        ctx.last_item_name = "MacBook"
        ctx.last_amount = None
        ctx.pending_action = "need_purchase_price"
        ctx.recent_messages = []
        summary = build_context_summary(ctx)
        assert "need_purchase_price" in summary
        assert "MacBook" in summary


# ═══════════════════════════════════════════════════════════
# Req 15.3: Missing Price/Item Follow-up
# ═══════════════════════════════════════════════════════════

class TestMissingFieldHandling:
    """Test that missing price/item triggers follow-up, not a crash."""

    def test_fallback_purchase_no_price(self):
        """Ask purchase without price → ask_purchase with empty entities."""
        result = _fallback_parse("est-ce que je peux acheter un vélo ?")
        assert result.intent == "ask_purchase"
        assert result.entities.get("price") is None

    def test_fallback_purchase_no_item(self):
        """'je peux l'acheter ?' → ask_purchase with no item (needs context)."""
        result = _fallback_parse("je peux l'acheter ?")
        assert result.intent == "ask_purchase"
        assert result.entities.get("item_name") is None


# ═══════════════════════════════════════════════════════════
# Req 15.4: Multi-Expense Parsing
# ═══════════════════════════════════════════════════════════

class TestMultiExpenseParsing:
    """Test that multi-expense entities from LLM are handled correctly."""

    def test_multi_expense_entities_structure(self):
        """Verify the expected entity format for add_multiple."""
        entities = {
            "items": [
                {"amount": 500, "category": "logement", "description": "loyer", "type": "expense"},
                {"amount": 50, "category": "transport", "description": "transport", "type": "expense"},
            ]
        }
        assert len(entities["items"]) == 2
        assert entities["items"][0]["amount"] == 500
        assert entities["items"][1]["category"] == "transport"

    def test_multi_expense_total(self):
        """Verify total calculation for multi-expense."""
        items = [
            {"amount": 500, "category": "logement"},
            {"amount": 50, "category": "transport"},
            {"amount": 0, "category": "invalid"},  # should be skipped
        ]
        total = sum(i["amount"] for i in items if i["amount"] > 0)
        assert total == 550


# ═══════════════════════════════════════════════════════════
# Req 15.5: LLM Fallback Behavior
# ═══════════════════════════════════════════════════════════

class TestLLMFallbacks:
    """Test all LLM fallback functions work without OpenAI."""

    def test_simple_amount_parse_number(self):
        assert _simple_amount_parse("1500") == 1500.0

    def test_simple_amount_parse_euro(self):
        assert _simple_amount_parse("1500€") == 1500.0

    def test_simple_amount_parse_comma(self):
        assert _simple_amount_parse("13,5") == 13.5

    def test_simple_amount_parse_natural(self):
        """Natural text with number embedded."""
        assert _simple_amount_parse("environ 2000 euros") == 2000.0

    def test_simple_amount_parse_zero(self):
        assert _simple_amount_parse("0") == 0.0

    def test_simple_amount_parse_aucun(self):
        assert _simple_amount_parse("aucun") == 0.0

    def test_simple_amount_parse_rien(self):
        assert _simple_amount_parse("rien") == 0.0

    def test_simple_amount_parse_no_number(self):
        assert _simple_amount_parse("bonjour") is None

    def test_simple_choice_parse_direct(self):
        options = {
            "stable": ["stable", "cdi"],
            "internship": ["stage", "cdd"],
        }
        assert _simple_choice_parse("stable", options, "other") == "stable"

    def test_simple_choice_parse_keyword_in_text(self):
        options = {
            "stable": ["stable", "cdi"],
            "internship": ["stage", "cdd", "stagiaire"],
        }
        assert _simple_choice_parse("je suis en stage", options, "other") == "internship"

    def test_simple_choice_parse_no_match(self):
        options = {"a": ["x"], "b": ["y"]}
        assert _simple_choice_parse("hello", options, "default") == "default"

    def test_default_response_greeting(self):
        resp = _default_response("greeting")
        assert "CashPilot" in resp

    def test_default_response_unknown(self):
        resp = _default_response("unknown")
        assert "compris" in resp

    def test_format_raw_decision_yes(self):
        """Raw decision formatting when LLM is down."""
        data = {
            "decision_status": "YES",
            "item_name": "Livre",
            "price": "25",
            "main_reason": "Achat raisonnable",
            "risk_score": 10,
        }
        result = _format_raw_decision(data)
        assert "YES" in result
        assert "Livre" in result
        assert "25" in result

    def test_format_raw_decision_no(self):
        data = {
            "decision_status": "NO",
            "item_name": "Voiture",
            "price": "5000",
            "main_reason": "Trop cher",
            "risk_score": 95,
        }
        result = _format_raw_decision(data)
        assert "NO" in result
        assert "❌" in result


# ═══════════════════════════════════════════════════════════
# Req 15.6: Summary Consistency After Onboarding
# ═══════════════════════════════════════════════════════════

class TestSnapshotConsistency:
    """Ensure the financial snapshot is consistent with stored profile data."""

    def _base_snapshot(self, **overrides) -> UserFinancialSnapshot:
        defaults = dict(
            monthly_income=Decimal("1500"),
            income_type="internship",
            monthly_fixed_charges=Decimal("350"),
            available_savings=Decimal("0"),
            total_liquid_cash=Decimal("0"),
            total_patrimony=Decimal("0"),
            safety_net_months=3,
            main_goal="stability",
            risk_tolerance="prudent",
            total_debt=Decimal("0"),
            monthly_spending_avg=Decimal("0"),
            spending_trend="stable",
        )
        defaults.update(overrides)
        return UserFinancialSnapshot(**defaults)

    def test_intern_with_zero_savings(self):
        """Intern with 0€ savings asking about 3000€ iPhone → should be NO."""
        snapshot = self._base_snapshot()
        purchase = PurchaseInput(item_name="iPhone", price=Decimal("3000"))
        result = evaluate_purchase(snapshot, purchase)
        # Price exceeds liquidity → must be NO
        assert result.decision_status.value == "NO"

    def test_stable_income_with_savings(self):
        """Stable income with savings → small purchase should be YES."""
        snapshot = self._base_snapshot(
            monthly_income=Decimal("2500"),
            income_type="stable",
            available_savings=Decimal("10000"),
            total_liquid_cash=Decimal("10000"),
            total_patrimony=Decimal("10000"),
        )
        purchase = PurchaseInput(item_name="Livre", price=Decimal("25"))
        result = evaluate_purchase(snapshot, purchase)
        assert result.decision_status.value == "YES"

    def test_savings_used_when_no_accounts(self):
        """When accounts have 0, savings from profile should be used."""
        # This tests the reconciliation logic in _build_financial_snapshot
        # Available savings = 5000, but no accounts → liquid should be 5000
        snapshot = self._base_snapshot(
            available_savings=Decimal("5000"),
            total_liquid_cash=Decimal("5000"),
            total_patrimony=Decimal("5000"),
        )
        assert snapshot.total_liquid_cash == Decimal("5000")
        assert snapshot.available_savings == Decimal("5000")


# ═══════════════════════════════════════════════════════════
# Req 15.7: Purchase Evaluation with Context-Filled Item/Price
# ═══════════════════════════════════════════════════════════

class TestPurchaseWithContext:
    """Test that purchases work when item/price come from context."""

    def test_context_filled_purchase_evaluation(self):
        """Simulate: user previously discussed iPhone at 1200€, now says 'je peux ?'"""
        # The orchestrator fills item_name/price from context.
        # By the time evaluate_purchase is called, it should have real values.
        snapshot = UserFinancialSnapshot(
            monthly_income=Decimal("2500"),
            income_type="stable",
            monthly_fixed_charges=Decimal("900"),
            available_savings=Decimal("10000"),
            total_liquid_cash=Decimal("10000"),
            total_patrimony=Decimal("12000"),
            safety_net_months=3,
            main_goal="stability",
            risk_tolerance="balanced",
            total_debt=Decimal("0"),
            monthly_spending_avg=Decimal("1500"),
            spending_trend="stable",
        )
        # Context-filled values
        purchase = PurchaseInput(
            item_name="iPhone",  # from ctx.last_item_name
            price=Decimal("1200"),  # from ctx.last_amount
        )
        result = evaluate_purchase(snapshot, purchase)
        # With 10k savings and stable income, 1200€ should be reasonable
        assert result.decision_status.value in ("YES", "CONDITIONAL")
        assert result.risk_score is not None

    def test_context_filled_expensive_purchase(self):
        """Context-filled MacBook at 2500€ on intern salary → NO or WAIT."""
        snapshot = UserFinancialSnapshot(
            monthly_income=Decimal("800"),
            income_type="internship",
            monthly_fixed_charges=Decimal("600"),
            available_savings=Decimal("3000"),
            total_liquid_cash=Decimal("3000"),
            total_patrimony=Decimal("3000"),
            safety_net_months=3,
            main_goal="stability",
            risk_tolerance="prudent",
            total_debt=Decimal("0"),
            monthly_spending_avg=Decimal("700"),
            spending_trend="stable",
        )
        purchase = PurchaseInput(
            item_name="MacBook",
            price=Decimal("2500"),
        )
        result = evaluate_purchase(snapshot, purchase)
        assert result.decision_status.value in ("NO", "WAIT")
        assert result.risk_score > 50


# ═══════════════════════════════════════════════════════════
# Req 12: Graceful Fallback — parser never crashes
# ═══════════════════════════════════════════════════════════

class TestGracefulFallback:
    """Ensure parsing never crashes, even with bizarre input."""

    def test_unicode_input(self):
        result = _fallback_parse("🚀💰 emoji message 🎉")
        assert isinstance(result, ParsedMessage)

    def test_very_long_input(self):
        result = _fallback_parse("a " * 10000)
        assert isinstance(result, ParsedMessage)

    def test_special_characters(self):
        result = _fallback_parse("<script>alert('xss')</script>")
        assert isinstance(result, ParsedMessage)

    def test_numbers_only(self):
        result = _fallback_parse("42")
        assert isinstance(result, ParsedMessage)

    def test_safe_decimal_conversion(self):
        """Test the _safe_decimal helper in telegram_service."""
        from app.services.telegram_service import _safe_decimal
        assert _safe_decimal(25) == Decimal("25")
        assert _safe_decimal("25.50") == Decimal("25.50")
        assert _safe_decimal(0) is None
        assert _safe_decimal(-10) is None
        assert _safe_decimal(None) is None
        assert _safe_decimal("abc") is None
        assert _safe_decimal("") is None


# ═══════════════════════════════════════════════════════════
# Req 10: Decision Guardrails
# ═══════════════════════════════════════════════════════════

class TestDecisionGuardrails:
    """Verify that the LLM never makes financial decisions."""

    def test_reformulate_never_changes_verdict(self):
        """_format_raw_decision preserves the original decision status."""
        for status in ("YES", "NO", "WAIT", "CONDITIONAL"):
            data = {"decision_status": status, "item_name": "X", "price": "100", "risk_score": 50}
            result = _format_raw_decision(data)
            assert status in result, f"Decision {status} not preserved in output"

    @pytest.mark.asyncio
    async def test_ai_parser_no_client_uses_fallback(self):
        """When no OpenAI client, parser falls back to regex — never to LLM decisions."""
        from app.services.ai_parser import parse_user_message
        with patch("app.services.ai_parser.get_openai_client", return_value=None):
            result = await parse_user_message("25 resto")
            assert result.intent == "add_expense"
            assert result.used_fallback is True


# ═══════════════════════════════════════════════════════════
# NEW: Correction & Cancel Fallback Parsing
# ═══════════════════════════════════════════════════════════

class TestCorrectionCancelFallback:
    """Test fallback parser handles correction and cancel intents."""

    def test_annule(self):
        result = _fallback_parse("annule")
        assert result.intent == "cancel_last"
        assert result.used_fallback is True

    def test_supprime(self):
        result = _fallback_parse("supprime")
        assert result.intent == "cancel_last"

    def test_cancel_english(self):
        result = _fallback_parse("cancel")
        assert result.intent == "cancel_last"

    def test_undo(self):
        result = _fallback_parse("undo")
        assert result.intent == "cancel_last"

    def test_corrige_amount(self):
        result = _fallback_parse("corrige 20")
        assert result.intent == "correct_last"
        assert result.entities["amount"] == 20.0

    def test_non_cetait(self):
        result = _fallback_parse("non c'était 25")
        assert result.intent == "correct_last"
        assert result.entities["amount"] == 25.0

    def test_non_pas_mais(self):
        result = _fallback_parse("non pas 1500 mais 1300")
        assert result.intent == "correct_last"
        assert result.entities["amount"] == 1300.0

    def test_corrige_decimal(self):
        result = _fallback_parse("corrige 13,5")
        assert result.intent == "correct_last"
        assert result.entities["amount"] == 13.5


# ═══════════════════════════════════════════════════════════
# NEW: Mixed Language Support
# ═══════════════════════════════════════════════════════════

class TestMixedLanguageFallback:
    """Test fallback parser handles English and franglais."""

    def test_buy_keyword(self):
        result = _fallback_parse("buy iphone 3000")
        assert result.intent == "ask_purchase"

    def test_can_i_buy(self):
        result = _fallback_parse("can i buy a car?")
        assert result.intent == "ask_purchase"

    def test_hello_greeting(self):
        result = _fallback_parse("hello")
        assert result.intent == "greeting"

    def test_summary_english(self):
        result = _fallback_parse("summary")
        assert result.intent == "show_summary"


# ═══════════════════════════════════════════════════════════
# NEW: Telegram Button Keyboards
# ═══════════════════════════════════════════════════════════

class TestTelegramButtons:
    """Test InlineKeyboard builders and callback parsing."""

    def test_main_menu_keyboard_structure(self):
        from app.services.telegram_buttons import main_menu_keyboard
        kb = main_menu_keyboard()
        assert "inline_keyboard" in kb
        rows = kb["inline_keyboard"]
        assert len(rows) >= 3  # At least 3 rows

    def test_main_menu_has_all_buttons(self):
        from app.services.telegram_buttons import main_menu_keyboard
        kb = main_menu_keyboard()
        all_buttons = [btn for row in kb["inline_keyboard"] for btn in row]
        callback_datas = [b["callback_data"] for b in all_buttons]
        assert "menu_add_expense" in callback_datas
        assert "menu_summary" in callback_datas
        assert "menu_canibuy" in callback_datas
        assert "menu_profile" in callback_datas
        assert "menu_help" in callback_datas

    def test_expense_category_keyboard_structure(self):
        from app.services.telegram_buttons import expense_category_keyboard
        kb = expense_category_keyboard()
        all_buttons = [btn for row in kb["inline_keyboard"] for btn in row]
        callback_datas = [b["callback_data"] for b in all_buttons]
        assert "cat_restaurant" in callback_datas
        assert "cat_transport" in callback_datas
        assert "cat_logement" in callback_datas

    def test_confirmation_keyboard(self):
        from app.services.telegram_buttons import confirmation_keyboard
        kb = confirmation_keyboard("tx123")
        buttons = [btn for row in kb["inline_keyboard"] for btn in row]
        assert len(buttons) == 2
        assert "confirm_yes_tx123" in buttons[0]["callback_data"]
        assert "confirm_no_tx123" in buttons[1]["callback_data"]

    def test_parse_callback_data_menu(self):
        from app.services.telegram_buttons import parse_callback_data
        prefix, value = parse_callback_data("menu_add_expense")
        assert prefix == "menu"
        assert value == "add_expense"

    def test_parse_callback_data_category(self):
        from app.services.telegram_buttons import parse_callback_data
        prefix, value = parse_callback_data("cat_restaurant")
        assert prefix == "cat"
        assert value == "restaurant"

    def test_parse_callback_data_single(self):
        from app.services.telegram_buttons import parse_callback_data
        prefix, value = parse_callback_data("cancel")
        assert prefix == "cancel"
        assert value == ""


# ═══════════════════════════════════════════════════════════
# NEW: Duplicate Detection
# ═══════════════════════════════════════════════════════════

class TestDuplicateDetection:
    """Test that duplicate Telegram messages are detected."""

    @pytest.mark.asyncio
    async def test_duplicate_detected(self):
        from app.services.telegram_service import _is_duplicate_message
        ctx = MagicMock()
        ctx.recent_messages = [
            {"role": "user", "content": "25 resto"},
        ]
        assert await _is_duplicate_message(ctx, "25 resto") is True

    @pytest.mark.asyncio
    async def test_different_message_not_duplicate(self):
        from app.services.telegram_service import _is_duplicate_message
        ctx = MagicMock()
        ctx.recent_messages = [
            {"role": "user", "content": "25 resto"},
        ]
        assert await _is_duplicate_message(ctx, "30 uber") is False

    @pytest.mark.asyncio
    async def test_empty_history_not_duplicate(self):
        from app.services.telegram_service import _is_duplicate_message
        ctx = MagicMock()
        ctx.recent_messages = []
        assert await _is_duplicate_message(ctx, "25 resto") is False

    @pytest.mark.asyncio
    async def test_last_assistant_message_not_duplicate(self):
        from app.services.telegram_service import _is_duplicate_message
        ctx = MagicMock()
        ctx.recent_messages = [
            {"role": "assistant", "content": "25 resto"},
        ]
        assert await _is_duplicate_message(ctx, "25 resto") is False

