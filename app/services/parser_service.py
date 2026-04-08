"""Parser service — extracts amount and category from free-text expense messages.

This is a deterministic parser (regex + keyword matching), not LLM-dependent.
"""

import re
from dataclasses import dataclass

# Category keywords mapping (French-first)
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "restaurant": [
        "resto", "restaurant", "restau", "mcdo", "mcdonald", "burger", "pizza",
        "sushi", "kebab", "brasserie", "bistrot", "cantine",
    ],
    "alimentation": [
        "courses", "supermarché", "supermarche", "marché", "marche", "carrefour",
        "lidl", "aldi", "monoprix", "franprix", "picard", "bio", "épicerie",
        "epicerie", "primeur", "boulangerie",
    ],
    "transport": [
        "uber", "taxi", "vtc", "metro", "métro", "bus", "train", "sncf",
        "essence", "carburant", "péage", "peage", "parking", "vélo", "velo",
        "trottinette", "bolt", "blablacar", "navigo",
    ],
    "logement": [
        "loyer", "rent", "electricité", "electricite", "edf", "gaz", "eau",
        "charges", "assurance habitation", "internet", "fibre", "box",
    ],
    "loisir": [
        "cinema", "cinéma", "concert", "spectacle", "jeux", "jeu", "netflix",
        "spotify", "disney", "sortie", "bar", "soirée", "soiree", "musée",
        "musee", "parc",
    ],
    "santé": [
        "medecin", "médecin", "pharmacie", "santé", "sante", "dentiste",
        "ophtalmo", "kiné", "kine", "hopital", "hôpital", "mutuelle",
    ],
    "abonnement": [
        "abonnement", "abo", "forfait", "mobile", "téléphone", "telephone",
        "cloud", "gym", "salle", "sport",
    ],
    "shopping": [
        "shopping", "vêtement", "vetement", "chaussure", "zara", "hm", "h&m",
        "uniqlo", "amazon", "fnac", "darty", "ikea", "meuble",
    ],
    "revenu": [
        "salaire", "salary", "freelance", "facture", "paye", "paie",
        "remboursement", "virement",
    ],
}

# Flatten for reverse lookup
_KEYWORD_TO_CATEGORY: dict[str, str] = {}
for cat, keywords in _CATEGORY_KEYWORDS.items():
    for kw in keywords:
        _KEYWORD_TO_CATEGORY[kw] = cat


@dataclass
class ParsedExpense:
    """Result of parsing a free-text expense message."""
    amount: float
    category: str
    description: str
    is_income: bool


def parse_expense(text: str) -> ParsedExpense | None:
    """Parse a free-text expense message like '25 resto' or 'café 13.5'.

    Supports patterns:
        - "25 resto"
        - "resto 25"
        - "13.5 café"
        - "café 13,5"
        - "25€ courses"
        - "+2500 salaire"  (income)

    Returns None if no valid amount/description found.
    """
    text = text.strip().lower()
    if not text:
        return None

    # Detect income
    is_income = text.startswith("+")
    if is_income:
        text = text.lstrip("+").strip()

    # Try patterns: <amount> <description> OR <description> <amount>
    # Amount pattern: digits with optional comma/dot decimal + optional €
    amount_pattern = r"(\d+(?:[.,]\d{1,2})?)€?"

    # Pattern 1: amount first → "25 resto"
    match = re.match(rf"^{amount_pattern}\s+(.+)$", text)
    if not match:
        # Pattern 2: description first → "resto 25"
        match = re.match(rf"^(.+?)\s+{amount_pattern}$", text)
        if match:
            desc_raw = match.group(1).strip()
            amount_raw = match.group(2)
        else:
            return None
    else:
        amount_raw = match.group(1)
        desc_raw = match.group(2).strip()

    if not match:
        return None

    if "amount_raw" not in dir():
        amount_raw = match.group(1)
        desc_raw = match.group(2).strip()

    # Parse amount
    amount_raw = amount_raw.replace(",", ".")
    try:
        amount = float(amount_raw)
    except ValueError:
        return None

    if amount <= 0:
        return None

    # Classify category
    category = _guess_category(desc_raw)

    if category == "revenu":
        is_income = True

    return ParsedExpense(
        amount=amount,
        category=category,
        description=desc_raw,
        is_income=is_income,
    )


def _guess_category(description: str) -> str:
    """Match description against keyword database."""
    desc_lower = description.lower().strip()

    # Exact match first
    if desc_lower in _KEYWORD_TO_CATEGORY:
        return _KEYWORD_TO_CATEGORY[desc_lower]

    # Partial match
    for keyword, category in _KEYWORD_TO_CATEGORY.items():
        if keyword in desc_lower or desc_lower in keyword:
            return category

    return "autre"
