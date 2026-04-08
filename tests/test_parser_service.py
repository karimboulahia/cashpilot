"""Tests for the parser service — expense message parsing."""

import pytest

from app.services.parser_service import parse_expense


class TestParseExpense:
    """Test free-text expense parsing."""

    def test_amount_first_simple(self):
        """'25 resto' → amount=25, category=restaurant."""
        result = parse_expense("25 resto")
        assert result is not None
        assert result.amount == 25.0
        assert result.category == "restaurant"
        assert not result.is_income

    def test_amount_first_decimal_dot(self):
        """'13.5 café' → amount=13.5."""
        result = parse_expense("13.5 café")
        assert result is not None
        assert result.amount == 13.5

    def test_amount_first_decimal_comma(self):
        """'13,5 café' → amount=13.5."""
        result = parse_expense("13,5 café")
        assert result is not None
        assert result.amount == 13.5

    def test_description_first(self):
        """'uber 18' → amount=18, category=transport."""
        result = parse_expense("uber 18")
        assert result is not None
        assert result.amount == 18.0
        assert result.category == "transport"

    def test_category_alimentation(self):
        """'45 courses' → category=alimentation."""
        result = parse_expense("45 courses")
        assert result is not None
        assert result.category == "alimentation"

    def test_category_logement(self):
        """'120 loyer' → category=logement."""
        result = parse_expense("120 loyer")
        assert result is not None
        assert result.category == "logement"

    def test_category_transport(self):
        """'18 uber' → category=transport."""
        result = parse_expense("18 uber")
        assert result is not None
        assert result.category == "transport"

    def test_unknown_category(self):
        """'50 truc' → category=autre."""
        result = parse_expense("50 truc")
        assert result is not None
        assert result.category == "autre"

    def test_income_detection(self):
        """'+2500 salaire' → is_income=True, category=revenu."""
        result = parse_expense("+2500 salaire")
        assert result is not None
        assert result.is_income is True
        assert result.category == "revenu"

    def test_amount_with_euro_sign(self):
        """'25€ courses' → amount=25."""
        result = parse_expense("25€ courses")
        assert result is not None
        assert result.amount == 25.0

    def test_empty_string(self):
        """Empty string → None."""
        assert parse_expense("") is None

    def test_no_amount(self):
        """'hello' → None."""
        assert parse_expense("hello") is None

    def test_zero_amount(self):
        """'0 resto' → None (invalid)."""
        assert parse_expense("0 resto") is None

    def test_category_shopping(self):
        """'200 zara' → category=shopping."""
        result = parse_expense("200 zara")
        assert result is not None
        assert result.category == "shopping"

    def test_category_sante(self):
        """'35 pharmacie' → category=santé."""
        result = parse_expense("35 pharmacie")
        assert result is not None
        assert result.category == "santé"
