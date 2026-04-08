"""LLM Service — OpenAI integration for NLU, entity extraction, and response reformulation.

The LLM does NOT make financial decisions. It:
1. Classifies user intent
2. Extracts entities from free text
3. Reformulates decision engine output into natural language
4. Suggests follow-up questions
"""

import json
from enum import Enum

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("llm_service")


class UserIntent(str, Enum):
    ONBOARDING_ANSWER = "onboarding_answer"
    ADD_EXPENSE = "add_expense"
    ADD_ACCOUNT = "add_account"
    ASK_PURCHASE_DECISION = "ask_purchase_decision"
    UPDATE_PROFILE = "update_profile"
    SHOW_SUMMARY = "show_summary"
    UNKNOWN = "unknown"


_INTENT_SYSTEM_PROMPT = """Tu es un assistant qui classifie les messages d'un utilisateur d'une app de gestion financière.

Réponds UNIQUEMENT avec un JSON valide (pas de markdown, pas de texte autour) :
{
  "intent": "<une des valeurs suivantes>",
  "confidence": <0.0 à 1.0>,
  "entities": {}
}

Intents possibles :
- "onboarding_answer" : l'utilisateur répond à une question d'onboarding (revenu, charges, situation...)
- "add_expense" : l'utilisateur note une dépense (ex: "25 resto", "18 uber")
- "add_account" : l'utilisateur veut ajouter un compte
- "ask_purchase_decision" : l'utilisateur demande s'il peut acheter quelque chose
- "update_profile" : l'utilisateur veut modifier son profil
- "show_summary" : l'utilisateur veut voir un résumé de sa situation
- "unknown" : tu ne sais pas

Pour "add_expense", extrais : {"amount": number, "description": "string"}
Pour "ask_purchase_decision", extrais : {"item_name": "string", "price": number, "category": "string"}
Pour "onboarding_answer", extrais la donnée dans entities."""


async def classify_intent(message: str) -> dict:
    """Classify user message intent and extract entities.

    Returns dict with keys: intent, confidence, entities.
    Falls back to simple parsing on error.
    """
    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        logger.warning("No OpenAI API key — falling back to simple classification")
        return _fallback_classify(message)

    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            temperature=0.1,
            max_tokens=300,
            timeout=10.0,
        )
        content = response.choices[0].message.content or "{}"
        # Strip markdown code fences if the model wraps the response
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(content)
        result.setdefault("intent", "unknown")
        result.setdefault("confidence", 0.5)
        result.setdefault("entities", {})
        return result
    except Exception as e:
        logger.error(f"LLM intent classification failed: {e}")
        return _fallback_classify(message)


async def reformulate_decision(decision_data: dict, user_context: str = "") -> str:
    """Use LLM to reformulate the decision engine's output into a natural message."""
    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        return decision_data.get("explanation_detailed", str(decision_data))

    prompt = (
        "Tu es CashPilot, un copilote financier bienveillant et direct. "
        "Reformule cette décision financière de manière naturelle, chaleureuse et actionnable. "
        "Utilise des emojis. Sois concis. Ne change PAS la décision.\n\n"
        f"Contexte utilisateur : {user_context}\n\n"
        f"Décision brute :\n{json.dumps(decision_data, ensure_ascii=False, indent=2)}"
    )

    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=500,
            timeout=15.0,
        )
        return response.choices[0].message.content or decision_data.get(
            "explanation_detailed", ""
        )
    except Exception as e:
        logger.error(f"LLM reformulation failed: {e}")
        return decision_data.get("explanation_detailed", str(decision_data))


async def generate_follow_up_questions(missing_info: list[str], context: str = "") -> str:
    """Use LLM to formulate natural follow-up questions."""
    settings = get_settings()
    if not settings.OPENAI_API_KEY or not missing_info:
        return "\n".join(f"❓ {q}" for q in missing_info)

    prompt = (
        "Tu es CashPilot. Pose ces questions de manière naturelle et bienveillante, "
        "comme un ami qui s'y connaît en finance. Une question par ligne, avec un emoji.\n\n"
        f"Infos manquantes : {json.dumps(missing_info, ensure_ascii=False)}\n"
        f"Contexte : {context}"
    )

    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "system", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
            timeout=10.0,
        )
        return response.choices[0].message.content or "\n".join(
            f"❓ {q}" for q in missing_info
        )
    except Exception as e:
        logger.error(f"LLM follow-up generation failed: {e}")
        return "\n".join(f"❓ {q}" for q in missing_info)


def _fallback_classify(message: str) -> dict:
    """Simple keyword-based fallback when LLM is unavailable."""
    msg = message.lower().strip()

    # Purchase decision keywords
    purchase_keywords = [
        "acheter", "achat", "est-ce que je peux", "puis-je", "canibuy",
        "je veux acheter", "j'aimerais acheter", "budget pour",
    ]
    for kw in purchase_keywords:
        if kw in msg:
            return {
                "intent": "ask_purchase_decision",
                "confidence": 0.6,
                "entities": {},
            }

    # Summary keywords
    summary_keywords = ["résumé", "resume", "summary", "situation", "bilan"]
    for kw in summary_keywords:
        if kw in msg:
            return {"intent": "show_summary", "confidence": 0.7, "entities": {}}

    # Expense pattern (number + text)
    import re
    if re.match(r"^\d+[.,]?\d*\s+\w+", msg) or re.match(r"^\w+\s+\d+[.,]?\d*", msg):
        return {"intent": "add_expense", "confidence": 0.7, "entities": {}}

    return {"intent": "unknown", "confidence": 0.3, "entities": {}}
