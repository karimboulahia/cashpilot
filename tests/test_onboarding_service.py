"""Tests for the onboarding service."""

import pytest

from app.services.onboarding_service import (
    OnboardingStep,
    get_next_step,
    should_ask_income_end_date,
    parse_income_type,
    parse_housing_situation,
    parse_safety_months,
    parse_main_goal,
    parse_risk_tolerance,
    parse_amount,
)


class TestOnboardingStepOrder:
    def test_first_step_is_welcome(self):
        assert get_next_step(None) == OnboardingStep.WELCOME

    def test_welcome_to_monthly_income(self):
        assert get_next_step("welcome") == OnboardingStep.MONTHLY_INCOME

    def test_last_step_is_completed(self):
        assert get_next_step("risk_tolerance") == OnboardingStep.COMPLETED

    def test_invalid_step_returns_welcome(self):
        assert get_next_step("nonexistent") == OnboardingStep.WELCOME


class TestIncomeEndDate:
    def test_internship_needs_end_date(self):
        assert should_ask_income_end_date("internship") is True

    def test_variable_needs_end_date(self):
        assert should_ask_income_end_date("variable") is True

    def test_stable_no_end_date(self):
        assert should_ask_income_end_date("stable") is False

    def test_freelance_no_end_date(self):
        assert should_ask_income_end_date("freelance") is False


class TestParsers:
    def test_parse_income_type_number(self):
        assert parse_income_type("1") == "stable"
        assert parse_income_type("3") == "internship"
        assert parse_income_type("5") == "none"

    def test_parse_income_type_text(self):
        assert parse_income_type("stable") == "stable"
        assert parse_income_type("freelance") == "freelance"
        assert parse_income_type("stage") == "internship"

    def test_parse_housing(self):
        assert parse_housing_situation("1") == "alone"
        assert parse_housing_situation("seul") == "alone"
        assert parse_housing_situation("coloc") == "shared"

    def test_parse_safety_months(self):
        assert parse_safety_months("1") == 1
        assert parse_safety_months("2") == 3
        assert parse_safety_months("3") == 6
        assert parse_safety_months("12") == 12

    def test_parse_main_goal(self):
        assert parse_main_goal("1") == "stability"
        assert parse_main_goal("voiture") == "car"
        assert parse_main_goal("voyage") == "travel"

    def test_parse_risk_tolerance(self):
        assert parse_risk_tolerance("1") == "prudent"
        assert parse_risk_tolerance("prudent") == "prudent"
        assert parse_risk_tolerance("3") == "aggressive"

    def test_parse_amount_simple(self):
        assert parse_amount("2500") == 2500.0

    def test_parse_amount_with_euro(self):
        assert parse_amount("2500€") == 2500.0

    def test_parse_amount_with_comma(self):
        assert parse_amount("2500,50") == 2500.5

    def test_parse_amount_invalid(self):
        assert parse_amount("abc") == 0.0

    def test_parse_amount_negative_returns_zero(self):
        assert parse_amount("-100") == 0.0
