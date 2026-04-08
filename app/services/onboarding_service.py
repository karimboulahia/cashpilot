"""Onboarding service — state machine for collecting user financial profile."""

from enum import Enum


class OnboardingStep(str, Enum):
    WELCOME = "welcome"
    MONTHLY_INCOME = "monthly_income"
    INCOME_TYPE = "income_type"
    INCOME_END_DATE = "income_end_date"
    MONTHLY_CHARGES = "monthly_charges"
    AVAILABLE_SAVINGS = "available_savings"
    TOTAL_DEBT = "total_debt"
    HOUSING_SITUATION = "housing_situation"
    SAFETY_NET_MONTHS = "safety_net_months"
    MAIN_GOAL = "main_goal"
    RISK_TOLERANCE = "risk_tolerance"
    COMPLETED = "completed"


# Questions for each step
ONBOARDING_QUESTIONS: dict[str, str] = {
    OnboardingStep.WELCOME: (
        "👋 Bienvenue sur CashPilot ! Je suis ton copilote financier.\n\n"
        "Je vais te poser quelques questions pour comprendre ta situation. "
        "Ça prend 2 minutes et ça me permet de te donner des conseils personnalisés.\n\n"
        "💰 Quel est ton revenu mensuel net (en €) ?"
    ),
    OnboardingStep.MONTHLY_INCOME: "💰 Quel est ton revenu mensuel net (en €) ?",
    OnboardingStep.INCOME_TYPE: (
        "📊 Quel type de revenu as-tu ?\n\n"
        "1️⃣ Stable (CDI, fonctionnaire)\n"
        "2️⃣ Variable (commissions, primes)\n"
        "3️⃣ Stage / CDD\n"
        "4️⃣ Freelance\n"
        "5️⃣ Sans revenu"
    ),
    OnboardingStep.INCOME_END_DATE: "📅 Quand se termine ton contrat/stage ? (ex: juin 2025)",
    OnboardingStep.MONTHLY_CHARGES: "🏠 Quel est le total de tes charges fixes mensuelles ? (loyer, abos, assurances...)",
    OnboardingStep.AVAILABLE_SAVINGS: "🏦 Combien d'épargne disponible as-tu au total ? (tous comptes confondus)",
    OnboardingStep.TOTAL_DEBT: "💳 As-tu des dettes en cours ? Si oui, quel montant total ? (0 si aucune)",
    OnboardingStep.HOUSING_SITUATION: (
        "🏡 Quelle est ta situation de logement ?\n\n"
        "1️⃣ Seul(e)\n"
        "2️⃣ En famille\n"
        "3️⃣ En colocation"
    ),
    OnboardingStep.SAFETY_NET_MONTHS: (
        "🛡️ Combien de mois de matelas de sécurité souhaites-tu ?\n\n"
        "1️⃣ 1 mois\n"
        "2️⃣ 3 mois (recommandé)\n"
        "3️⃣ 6 mois\n"
        "4️⃣ Autre (précise)"
    ),
    OnboardingStep.MAIN_GOAL: (
        "🎯 Quel est ton objectif financier principal ?\n\n"
        "1️⃣ Stabilité financière\n"
        "2️⃣ Acheter une voiture\n"
        "3️⃣ Voyage\n"
        "4️⃣ Investissement\n"
        "5️⃣ Rembourser une dette\n"
        "6️⃣ Autre"
    ),
    OnboardingStep.RISK_TOLERANCE: (
        "⚖️ Quelle est ta tolérance au risque ?\n\n"
        "1️⃣ Prudent — je protège mon capital\n"
        "2️⃣ Équilibré — un bon mix sécurité/opportunité\n"
        "3️⃣ Agressif — je vise la croissance"
    ),
    OnboardingStep.COMPLETED: (
        "✅ Profil complété ! Je connais maintenant ta situation.\n\n"
        "Tu peux :\n"
        "• Envoyer tes dépenses : \"25 resto\", \"18 uber\"\n"
        "• Demander un avis : /canibuy\n"
        "• Voir ton résumé : /summary\n"
        "• Ajouter un compte : /add_account\n\n"
        "💡 Commence par noter tes dépenses du jour !"
    ),
}

# Step order
_STEP_ORDER = list(OnboardingStep)


def get_next_step(current_step: str | None) -> OnboardingStep:
    """Get the next onboarding step."""
    if current_step is None:
        return OnboardingStep.WELCOME

    try:
        current = OnboardingStep(current_step)
    except ValueError:
        return OnboardingStep.WELCOME

    idx = _STEP_ORDER.index(current)
    if idx + 1 < len(_STEP_ORDER):
        return _STEP_ORDER[idx + 1]
    return OnboardingStep.COMPLETED


def should_ask_income_end_date(income_type: str) -> bool:
    """Only ask for end date if income is temporary."""
    return income_type in ("internship", "variable")


def parse_income_type(answer: str) -> str:
    """Parse income type from user answer."""
    mapping = {
        "1": "stable", "stable": "stable", "cdi": "stable",
        "2": "variable", "variable": "variable",
        "3": "internship", "stage": "internship", "cdd": "internship",
        "4": "freelance", "freelance": "freelance",
        "5": "none", "sans": "none", "aucun": "none",
    }
    return mapping.get(answer.lower().strip(), "stable")


def parse_housing_situation(answer: str) -> str:
    """Parse housing from user answer."""
    mapping = {
        "1": "alone", "seul": "alone", "seule": "alone",
        "2": "family", "famille": "family",
        "3": "shared", "colocation": "shared", "coloc": "shared",
    }
    return mapping.get(answer.lower().strip(), "alone")


def parse_safety_months(answer: str) -> int:
    """Parse safety net months from user answer."""
    mapping = {"1": 1, "2": 3, "3": 6}
    if answer.strip() in mapping:
        return mapping[answer.strip()]
    try:
        return max(1, int(answer.strip()))
    except ValueError:
        return 3


def parse_main_goal(answer: str) -> str:
    """Parse main goal from user answer."""
    mapping = {
        "1": "stability", "stabilité": "stability", "stabilite": "stability",
        "2": "car", "voiture": "car",
        "3": "travel", "voyage": "travel",
        "4": "investment", "investissement": "investment",
        "5": "pay_debt", "dette": "pay_debt", "rembourser": "pay_debt",
        "6": "other", "autre": "other",
    }
    return mapping.get(answer.lower().strip(), "other")


def parse_risk_tolerance(answer: str) -> str:
    """Parse risk tolerance from user answer."""
    mapping = {
        "1": "prudent", "prudent": "prudent",
        "2": "balanced", "équilibré": "balanced", "equilibre": "balanced",
        "3": "aggressive", "agressif": "aggressive",
    }
    return mapping.get(answer.lower().strip(), "balanced")


def parse_amount(answer: str) -> float:
    """Parse a monetary amount from user answer."""
    cleaned = answer.strip().replace("€", "").replace(",", ".").replace(" ", "")
    try:
        return max(0.0, float(cleaned))
    except ValueError:
        return 0.0
