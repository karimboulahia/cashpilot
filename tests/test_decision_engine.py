"""Tests for the decision engine — core business rules."""

import pytest
from decimal import Decimal

from app.services.decision_engine import (
    UserFinancialSnapshot,
    PurchaseInput,
    evaluate_purchase,
    get_missing_questions,
)


def _base_snapshot(**overrides) -> UserFinancialSnapshot:
    """Create a base snapshot with defaults, easily overridable."""
    defaults = dict(
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
    defaults.update(overrides)
    return UserFinancialSnapshot(**defaults)


class TestDecisionEngineYES:
    """Cases where the engine should approve the purchase."""

    def test_stable_income_reasonable_purchase(self):
        """Cas 2: Revenu stable, bonne liquidité, achat téléphone 700€."""
        snapshot = _base_snapshot()
        purchase = PurchaseInput(
            item_name="iPhone",
            price=Decimal("700"),
            essentiality="useful",
        )
        result = evaluate_purchase(snapshot, purchase)
        assert result.decision_status.value == "YES"
        assert result.confidence_score > 50
        assert result.risk_score < 50

    def test_small_purchase_well_funded(self):
        """Petit achat avec finances solides."""
        snapshot = _base_snapshot(available_savings=Decimal("20000"), total_liquid_cash=Decimal("20000"))
        purchase = PurchaseInput(item_name="Livre", price=Decimal("25"))
        result = evaluate_purchase(snapshot, purchase)
        assert result.decision_status.value == "YES"
        assert result.risk_score < 20


class TestDecisionEngineNO:
    """Cases where the engine should reject the purchase."""

    def test_price_exceeds_liquidity(self):
        """Prix > liquidité → NO."""
        snapshot = _base_snapshot(total_liquid_cash=Decimal("500"), available_savings=Decimal("500"))
        purchase = PurchaseInput(item_name="MacBook", price=Decimal("2000"))
        result = evaluate_purchase(snapshot, purchase)
        assert result.decision_status.value == "NO"
        assert "liquidité" in result.main_reason.lower()

    def test_internship_car_purchase(self):
        """Cas 1: Stage + achat voiture 5000€ sur 9000€ d'épargne → NO."""
        snapshot = _base_snapshot(
            monthly_income=Decimal("800"),
            income_type="internship",
            available_savings=Decimal("9000"),
            total_liquid_cash=Decimal("9000"),
            monthly_fixed_charges=Decimal("600"),
            safety_net_months=3,
        )
        purchase = PurchaseInput(
            item_name="Voiture",
            price=Decimal("5000"),
            essentiality="useful",
            recurring_cost_estimate=Decimal("200"),
        )
        result = evaluate_purchase(snapshot, purchase)
        assert result.decision_status.value in ("NO", "WAIT")

    def test_unstable_income_comfort_purchase_high_savings_pct(self):
        """Revenu instable + achat confort + >40% de l'épargne → NO."""
        snapshot = _base_snapshot(
            income_type="freelance",
            available_savings=Decimal("3000"),
            total_liquid_cash=Decimal("3000"),
        )
        purchase = PurchaseInput(
            item_name="Console",
            price=Decimal("1500"),
            essentiality="comfort",
        )
        result = evaluate_purchase(snapshot, purchase)
        assert result.decision_status.value == "NO"

    def test_high_recurring_costs(self):
        """Coûts récurrents trop élevés par rapport au reste à vivre → NO."""
        snapshot = _base_snapshot(
            monthly_income=Decimal("2000"),
            monthly_fixed_charges=Decimal("1500"),
        )
        purchase = PurchaseInput(
            item_name="Abonnement premium",
            price=Decimal("100"),
            recurring_cost_estimate=Decimal("300"),
        )
        result = evaluate_purchase(snapshot, purchase)
        assert result.decision_status.value == "NO"


class TestDecisionEngineWAIT:
    """Cases where the engine should suggest waiting."""

    def test_breaks_safety_cushion_stable_income(self):
        """Achat qui casse le matelas de sécurité, revenu stable → WAIT."""
        snapshot = _base_snapshot(
            monthly_fixed_charges=Decimal("1000"),
            safety_net_months=3,
            available_savings=Decimal("4000"),
            total_liquid_cash=Decimal("4000"),
        )
        purchase = PurchaseInput(
            item_name="Vélo électrique",
            price=Decimal("2000"),
            essentiality="comfort",
        )
        result = evaluate_purchase(snapshot, purchase)
        assert result.decision_status.value == "WAIT"

    def test_goal_conflict(self):
        """Achat compromet un objectif actif → WAIT."""
        snapshot = _base_snapshot(
            monthly_income=Decimal("2000"),
            monthly_fixed_charges=Decimal("1200"),
            available_savings=Decimal("5000"),
            total_liquid_cash=Decimal("5000"),
            active_goals=[
                {"name": "Voyage", "remaining": "4000", "deadline_months": 6},
            ],
        )
        purchase = PurchaseInput(
            item_name="Sneakers",
            price=Decimal("900"),
            essentiality="impulse",
        )
        result = evaluate_purchase(snapshot, purchase)
        assert result.decision_status.value in ("WAIT", "NO")


class TestDecisionEngineCONDITIONAL:
    """Cases where the engine should give a conditional approval."""

    def test_essential_but_expensive(self):
        """Achat essentiel mais > 30% de l'épargne → CONDITIONAL."""
        snapshot = _base_snapshot(
            available_savings=Decimal("5000"),
            total_liquid_cash=Decimal("5000"),
        )
        purchase = PurchaseInput(
            item_name="Réfrigérateur",
            price=Decimal("2000"),
            essentiality="essential",
        )
        result = evaluate_purchase(snapshot, purchase)
        assert result.decision_status.value == "CONDITIONAL"
        assert result.recommended_max_budget is not None
        assert result.recommended_max_budget < purchase.price


class TestDecisionEngineSpendingDiscipline:
    """Cas 3: Comportement dépensier doit peser sur le score."""

    def test_increasing_spending_raises_risk(self):
        """Tendance de dépense en hausse augmente le risk_score."""
        snapshot_stable = _base_snapshot(spending_trend="stable")
        snapshot_increasing = _base_snapshot(spending_trend="increasing")
        purchase = PurchaseInput(item_name="Restaurant", price=Decimal("80"))

        result_stable = evaluate_purchase(snapshot_stable, purchase)
        result_increasing = evaluate_purchase(snapshot_increasing, purchase)

        assert result_increasing.risk_score > result_stable.risk_score


class TestMissingQuestions:
    """Test missing information detection."""

    def test_missing_income(self):
        snapshot = _base_snapshot(monthly_income=Decimal("0"))
        purchase = PurchaseInput(item_name="PC", price=Decimal("1000"))
        questions = get_missing_questions(snapshot, purchase)
        assert any("revenu" in q.lower() for q in questions)

    def test_expensive_purchase_asks_recurring(self):
        snapshot = _base_snapshot()
        purchase = PurchaseInput(item_name="Voiture", price=Decimal("15000"))
        questions = get_missing_questions(snapshot, purchase)
        assert any("récurrent" in q.lower() or "entretien" in q.lower() for q in questions)

    def test_internship_asks_guarantee(self):
        snapshot = _base_snapshot(income_type="internship")
        purchase = PurchaseInput(item_name="PC", price=Decimal("1000"))
        questions = get_missing_questions(snapshot, purchase)
        assert any("stage" in q.lower() or "garanti" in q.lower() for q in questions)
