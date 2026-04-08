"""Decision engine — deterministic purchase decision logic.

This is the CORE of CashPilot. All financial rules are coded here.
The LLM is NEVER used to make the actual decision.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.schemas.purchase_decision import DecisionResult, DecisionStatus


@dataclass
class UserFinancialSnapshot:
    """Aggregated financial snapshot used by the engine."""
    monthly_income: Decimal = Decimal("0")
    income_type: str = "stable"  # stable / variable / internship / freelance / none
    income_end_date: str | None = None
    monthly_fixed_charges: Decimal = Decimal("0")
    available_savings: Decimal = Decimal("0")
    total_debt: Decimal = Decimal("0")
    safety_net_months: int = 3
    main_goal: str = "stability"
    risk_tolerance: str = "balanced"  # prudent / balanced / aggressive

    # Computed from accounts
    total_liquid_cash: Decimal = Decimal("0")
    total_patrimony: Decimal = Decimal("0")

    # Computed from transactions
    monthly_spending_avg: Decimal = Decimal("0")
    spending_trend: str = "stable"  # increasing / stable / decreasing
    top_spending_categories: list[dict[str, Any]] = field(default_factory=list)

    # Goals
    active_goals: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PurchaseInput:
    """What the user wants to buy."""
    item_name: str
    price: Decimal
    item_category: str = "autre"
    payment_type: str = "cash"  # cash / installments
    essentiality: str = "comfort"  # essential / useful / comfort / impulse
    recurring_cost_estimate: Decimal = Decimal("0")


def evaluate_purchase(
    snapshot: UserFinancialSnapshot,
    purchase: PurchaseInput,
) -> DecisionResult:
    """Run all business rules and return a structured decision.

    This function is pure — no DB, no IO, fully testable.
    """
    risk_factors: list[str] = []
    positives: list[str] = []
    missing_info: list[str] = []

    monthly_disposable = snapshot.monthly_income - snapshot.monthly_fixed_charges
    safety_target = snapshot.monthly_fixed_charges * snapshot.safety_net_months
    post_purchase_liquid = snapshot.total_liquid_cash - purchase.price
    post_purchase_savings = snapshot.available_savings - purchase.price

    # ── Collect missing information ──────────────────────
    if snapshot.monthly_income == 0:
        missing_info.append("Revenu mensuel non renseigné")
    if snapshot.total_liquid_cash == 0 and snapshot.available_savings == 0:
        missing_info.append("Aucun compte ou épargne renseigné")
    if purchase.essentiality == "comfort" and purchase.price > Decimal("200"):
        missing_info.append("Est-ce un besoin ou une envie ?")
    if purchase.recurring_cost_estimate == 0 and purchase.price > Decimal("500"):
        missing_info.append("As-tu estimé les coûts récurrents (assurance, entretien, abonnements) ?")
    if snapshot.income_type in ("internship", "freelance") and not snapshot.income_end_date:
        missing_info.append("Ton revenu actuel est-il garanti après ta période actuelle ?")

    # ── RULE 1: Can't afford — price > liquid cash ───────
    if purchase.price > snapshot.total_liquid_cash and purchase.price > snapshot.available_savings:
        risk_factors.append("Le prix dépasse ta liquidité disponible")
        return DecisionResult(
            decision_status=DecisionStatus.NO,
            confidence_score=95,
            risk_score=95,
            main_reason="Tu n'as pas assez de liquidité pour cet achat.",
            risk_factors=risk_factors,
            positives=positives,
            missing_information=missing_info,
            explanation_short="❌ Achat impossible — liquidité insuffisante.",
            explanation_detailed=(
                f"L'achat de {purchase.item_name} à {purchase.price}€ dépasse ta liquidité "
                f"disponible de {snapshot.total_liquid_cash}€. Il faudrait d'abord épargner davantage."
            ),
            alternative_suggestion=f"Économise {purchase.price - snapshot.total_liquid_cash}€ de plus avant cet achat.",
        )

    # ── RULE 2: Breaks safety cushion ────────────────────
    if post_purchase_liquid < safety_target:
        cushion_deficit = safety_target - post_purchase_liquid
        risk_factors.append(
            f"L'achat te fait passer sous ton matelas de sécurité cible ({safety_target}€)"
        )

        if snapshot.income_type in ("internship", "none", "freelance"):
            risk_factors.append("Revenu instable — matelas de sécurité critique")
            return DecisionResult(
                decision_status=DecisionStatus.NO,
                confidence_score=90,
                risk_score=85,
                main_reason="Cet achat compromettrait ton matelas de sécurité avec un revenu instable.",
                risk_factors=risk_factors,
                positives=positives,
                missing_information=missing_info,
                explanation_short="❌ Trop risqué — protège ton matelas de sécurité.",
                explanation_detailed=(
                    f"Avec un revenu {snapshot.income_type} et un matelas cible de {safety_target}€, "
                    f"acheter {purchase.item_name} à {purchase.price}€ te laisserait {post_purchase_liquid}€ "
                    f"de liquidité, soit {cushion_deficit}€ sous ton objectif de sécurité."
                ),
                alternative_suggestion="Attends d'avoir un revenu plus stable ou d'avoir constitué un matelas suffisant.",
            )

        # Stable income but breaks cushion → WAIT
        if purchase.essentiality not in ("essential",):
            return DecisionResult(
                decision_status=DecisionStatus.WAIT,
                confidence_score=75,
                risk_score=65,
                main_reason="L'achat ferait passer ton épargne sous ton matelas de sécurité.",
                risk_factors=risk_factors,
                positives=positives,
                missing_information=missing_info,
                explanation_short="⏳ Attends un peu — tu passes sous ton matelas de sécurité.",
                explanation_detailed=(
                    f"Acheter {purchase.item_name} pour {purchase.price}€ te laisserait {post_purchase_liquid}€. "
                    f"Ton matelas de sécurité cible est de {safety_target}€. "
                    f"Avec ton revenu stable, tu pourrais te le permettre dans quelques mois."
                ),
                alternative_suggestion=(
                    f"Épargne encore {cushion_deficit}€ pour maintenir ton matelas, puis fais l'achat."
                ),
            )

    # ── RULE 3: Unstable income + non-essential + high % of savings ─
    savings_pct = (
        (purchase.price / snapshot.available_savings * 100)
        if snapshot.available_savings > 0
        else Decimal("100")
    )
    if (
        snapshot.income_type in ("variable", "freelance", "internship", "none")
        and purchase.essentiality in ("comfort", "impulse")
        and savings_pct > 40
    ):
        risk_factors.append(f"L'achat représente {savings_pct:.0f}% de ton épargne avec un revenu instable")
        return DecisionResult(
            decision_status=DecisionStatus.NO,
            confidence_score=85,
            risk_score=80,
            main_reason="Achat non essentiel trop important par rapport à ton épargne avec un revenu instable.",
            risk_factors=risk_factors,
            positives=positives,
            missing_information=missing_info,
            explanation_short="❌ Trop risqué — revenu instable et achat non essentiel.",
            explanation_detailed=(
                f"Ton revenu est {snapshot.income_type} et l'achat de {purchase.item_name} "
                f"représente {savings_pct:.0f}% de ton épargne. C'est trop risqué pour un achat "
                f"de type '{purchase.essentiality}'."
            ),
            alternative_suggestion="Limite-toi aux dépenses essentielles tant que ton revenu n'est pas stabilisé.",
        )

    # ── RULE 4: High savings percentage → elevated risk ──
    if savings_pct > 40:
        risk_factors.append(f"L'achat consomme {savings_pct:.0f}% de ton épargne liquide")

    # ── RULE 5: Recurring costs vs disposable income ─────
    if purchase.recurring_cost_estimate > 0:
        recurring_ratio = (
            purchase.recurring_cost_estimate / monthly_disposable * 100
            if monthly_disposable > 0
            else Decimal("100")
        )
        if recurring_ratio > 30:
            risk_factors.append(
                f"Coûts récurrents ({purchase.recurring_cost_estimate}€/mois) = "
                f"{recurring_ratio:.0f}% de ton reste à vivre"
            )
            if monthly_disposable <= 0 or recurring_ratio > 50:
                return DecisionResult(
                    decision_status=DecisionStatus.NO,
                    confidence_score=85,
                    risk_score=80,
                    main_reason="Les coûts récurrents sont trop élevés par rapport à ton reste à vivre.",
                    risk_factors=risk_factors,
                    positives=positives,
                    missing_information=missing_info,
                    explanation_short="❌ Les charges mensuelles liées seraient trop lourdes.",
                    explanation_detailed=(
                        f"Les coûts récurrents de {purchase.recurring_cost_estimate}€/mois "
                        f"pour {purchase.item_name} représenteraient {recurring_ratio:.0f}% de "
                        f"ton reste à vivre ({monthly_disposable}€/mois). Ce n'est pas tenable."
                    ),
                    alternative_suggestion="Cherche une option avec des coûts récurrents plus faibles.",
                )

    # ── RULE 6: Essential but too expensive → CONDITIONAL ─
    if purchase.essentiality == "essential" and savings_pct > 30:
        max_budget = snapshot.available_savings * Decimal("0.25")
        risk_factors.append("Achat essentiel mais cher par rapport à l'épargne")
        return DecisionResult(
            decision_status=DecisionStatus.CONDITIONAL,
            confidence_score=70,
            risk_score=55,
            recommended_max_budget=max_budget,
            main_reason="C'est un besoin essentiel, mais le montant est élevé.",
            risk_factors=risk_factors,
            positives=["C'est un achat essentiel — il faut le faire"],
            missing_information=missing_info,
            explanation_short=f"✅ Oui, mais avec un budget max recommandé de {max_budget:.0f}€.",
            explanation_detailed=(
                f"{purchase.item_name} est essentiel, mais à {purchase.price}€ ça représente "
                f"{savings_pct:.0f}% de ton épargne. On te recommande de viser {max_budget:.0f}€ max."
            ),
            alternative_suggestion=f"Cherche une option autour de {max_budget:.0f}€ ou moins.",
        )

    # ── RULE 7: Goal conflict ────────────────────────────
    for goal in snapshot.active_goals:
        remaining = Decimal(str(goal.get("remaining", 0)))
        deadline_months = goal.get("deadline_months")
        goal_name = goal.get("name", "objectif")

        if deadline_months and deadline_months <= 12 and remaining > 0:
            monthly_needed = remaining / deadline_months
            if purchase.price > monthly_disposable - monthly_needed:
                risk_factors.append(
                    f"Achat compromet l'objectif '{goal_name}' "
                    f"(il te faut {monthly_needed:.0f}€/mois pendant {deadline_months} mois)"
                )
                if purchase.essentiality in ("comfort", "impulse"):
                    return DecisionResult(
                        decision_status=DecisionStatus.WAIT,
                        confidence_score=70,
                        risk_score=60,
                        main_reason=f"Cet achat compromettrait ton objectif '{goal_name}'.",
                        risk_factors=risk_factors,
                        positives=positives,
                        missing_information=missing_info,
                        explanation_short=f"⏳ Attends — tu risques de compromettre ton objectif '{goal_name}'.",
                        explanation_detailed=(
                            f"Pour atteindre ton objectif '{goal_name}' dans {deadline_months} mois, "
                            f"tu dois mettre {monthly_needed:.0f}€/mois de côté. "
                            f"L'achat de {purchase.item_name} à {purchase.price}€ mettrait ça en danger."
                        ),
                        alternative_suggestion=f"Attends d'avoir atteint ton objectif '{goal_name}' ou repousse-le.",
                    )

    # ── RULE 8: Spending discipline check ────────────────
    if snapshot.spending_trend == "increasing":
        risk_factors.append("Tes dépenses sont en hausse récemment")

    # ── Composite score ──────────────────────────────────
    risk_score = _compute_risk_score(snapshot, purchase, savings_pct)
    confidence_score = 100 - risk_score

    # Collect positives
    if post_purchase_liquid >= safety_target:
        positives.append("Tu gardes ton matelas de sécurité intact")
    if snapshot.income_type == "stable":
        positives.append("Revenu stable")
    if savings_pct < 20:
        positives.append(f"L'achat ne représente que {savings_pct:.0f}% de ton épargne")
    if purchase.essentiality in ("essential", "useful"):
        positives.append("C'est un achat utile/essentiel")
    if monthly_disposable > snapshot.monthly_fixed_charges:
        positives.append("Bon reste à vivre")

    # ── RULE 9: All clear → YES ──────────────────────────
    return DecisionResult(
        decision_status=DecisionStatus.YES,
        confidence_score=confidence_score,
        risk_score=risk_score,
        main_reason="L'achat est compatible avec ta situation financière.",
        risk_factors=risk_factors,
        positives=positives,
        missing_information=missing_info,
        explanation_short=f"✅ Tu peux acheter {purchase.item_name} !",
        explanation_detailed=(
            f"L'achat de {purchase.item_name} à {purchase.price}€ est raisonnable. "
            f"Il te restera {post_purchase_liquid}€ de liquidité "
            f"(matelas de sécurité cible : {safety_target}€). "
            + (f"Risques identifiés : {', '.join(risk_factors)}. " if risk_factors else "")
            + (f"Points positifs : {', '.join(positives)}." if positives else "")
        ),
        alternative_suggestion=None,
    )


def _compute_risk_score(
    snapshot: UserFinancialSnapshot,
    purchase: PurchaseInput,
    savings_pct: Decimal,
) -> int:
    """Composite risk score 0-100 based on multiple dimensions."""
    score = 0

    # 1. Income stability (0-25)
    income_scores = {
        "stable": 0,
        "variable": 10,
        "freelance": 15,
        "internship": 20,
        "none": 25,
    }
    score += income_scores.get(snapshot.income_type, 10)

    # 2. Post-purchase safety (0-25)
    safety_target = snapshot.monthly_fixed_charges * snapshot.safety_net_months
    if safety_target > 0:
        post_liquid = snapshot.total_liquid_cash - purchase.price
        safety_ratio = float(post_liquid / safety_target)
        if safety_ratio >= 2:
            score += 0
        elif safety_ratio >= 1:
            score += 5
        elif safety_ratio >= 0.5:
            score += 15
        else:
            score += 25
    else:
        score += 10

    # 3. Savings consumption (0-25)
    pct = float(savings_pct)
    if pct < 10:
        score += 0
    elif pct < 20:
        score += 5
    elif pct < 40:
        score += 15
    else:
        score += 25

    # 4. Recurring cost burden (0-15)
    if purchase.recurring_cost_estimate > 0:
        disposable = snapshot.monthly_income - snapshot.monthly_fixed_charges
        if disposable > 0:
            ratio = float(purchase.recurring_cost_estimate / disposable * 100)
            if ratio < 10:
                score += 0
            elif ratio < 20:
                score += 5
            else:
                score += 15
        else:
            score += 15

    # 5. Spending discipline (0-10)
    if snapshot.spending_trend == "increasing":
        score += 10
    elif snapshot.spending_trend == "stable":
        score += 3

    return min(score, 100)


def get_missing_questions(
    snapshot: UserFinancialSnapshot,
    purchase: PurchaseInput,
) -> list[str]:
    """Determine which questions to ask before making a decision."""
    questions: list[str] = []

    if snapshot.monthly_income == 0:
        questions.append("Quel est ton revenu mensuel net ?")

    if snapshot.total_liquid_cash == 0 and snapshot.available_savings == 0:
        questions.append("Combien as-tu de disponible sur tes comptes ?")

    if purchase.essentiality == "comfort" and purchase.price > Decimal("200"):
        questions.append("Est-ce un besoin ou une envie ?")

    if snapshot.income_type in ("internship",) and not snapshot.income_end_date:
        questions.append("Ton revenu actuel est-il garanti après ton stage ?")

    if purchase.recurring_cost_estimate == 0 and purchase.price > Decimal("500"):
        questions.append("As-tu estimé les frais récurrents (assurance, entretien, etc.) ?")

    if purchase.price > Decimal("1000"):
        questions.append("Peux-tu trouver moins cher ou d'occasion ?")

    if purchase.price > snapshot.monthly_income and snapshot.monthly_income > 0:
        questions.append("As-tu une autre grosse dépense prévue bientôt ?")

    return questions
