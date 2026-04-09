"""LLM Service — OpenAI integration for response generation and reformulation.

GUARDRAIL: The LLM does NOT make financial decisions. It only:
  1. Reformulates decision engine output into natural language
  2. Generates conversational responses (greetings, chat)
  3. Formulates follow-up questions naturally
  4. Extracts amounts/choices from natural language

The financial verdict always comes from decision_engine.evaluate_purchase().
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("llm_service")

# ── Singleton OpenAI client ──────────────────────────────
_client: AsyncOpenAI | None = None
_client_initialized: bool = False


def get_openai_client() -> AsyncOpenAI | None:
    """Get or create the singleton OpenAI client."""
    global _client, _client_initialized
    if _client_initialized:
        return _client

    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        logger.warning("[LLM] No OPENAI_API_KEY configured — LLM features disabled")
        _client = None
    else:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        logger.info("[LLM] OpenAI client initialized")

    _client_initialized = True
    return _client


def get_model_name() -> str:
    """Get the configured model name."""
    return get_settings().OPENAI_MODEL


# ── Prompt loading ───────────────────────────────────────
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_prompt_cache: dict[str, str] = {}


def _load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory with caching."""
    if filename not in _prompt_cache:
        path = _PROMPTS_DIR / filename
        if path.exists():
            _prompt_cache[filename] = path.read_text(encoding="utf-8")
        else:
            logger.warning(f"[LLM] Prompt file not found: {path}")
            _prompt_cache[filename] = ""
    return _prompt_cache[filename]


# ── Response generation ──────────────────────────────────

async def generate_conversational_response(
    intent: str,
    user_message: str,
    context_summary: str = "",
    financial_summary: str = "",
) -> str:
    """Generate a natural conversational response using LLM.

    Used for greetings, general chat, and unknown intents.
    NEVER raises — returns fallback on error.
    """
    client = get_openai_client()
    if not client:
        logger.info("[LLM] No client — using default response")
        return _default_response(intent)

    system_prompt = _load_prompt("system_prompt.txt")
    if not system_prompt:
        system_prompt = (
            "Tu es CashPilot, un copilote financier bienveillant et direct sur Telegram. "
            "Réponds en français, avec des emojis, de manière concise et actionnable."
        )

    user_prompt = f"Message: {user_message}"
    if context_summary:
        user_prompt += f"\n\nContexte de conversation:\n{context_summary}"
    if financial_summary:
        user_prompt += f"\n\nSituation financière:\n{financial_summary}"

    t0 = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=get_model_name(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=300,
            timeout=10.0,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        result = response.choices[0].message.content or _default_response(intent)
        logger.info(f"[LLM] conversational response: {elapsed_ms}ms, {len(result)} chars")
        return result
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(f"[LLM] conversational response failed: {type(e).__name__}: {e} ({elapsed_ms}ms)")
        return _default_response(intent)


async def reformulate_decision(
    decision_data: dict,
    user_context: str = "",
    financial_profile: str = "",
) -> str:
    """Use LLM to reformulate the decision engine's output into a natural message.

    GUARDRAIL: The decision (YES/NO/WAIT/CONDITIONAL) is LOCKED. The LLM can
    only rephrase — it cannot change the verdict, risk score, or recommendation.
    NEVER raises — returns raw decision data on error.
    """
    client = get_openai_client()
    if not client:
        logger.info("[LLM] No client — returning raw decision explanation")
        return _format_raw_decision(decision_data)

    prompt_template = _load_prompt("explain_decision_prompt.txt")
    if prompt_template and "{decision_data}" in prompt_template:
        prompt = prompt_template.format(
            decision_data=json.dumps(decision_data, ensure_ascii=False, indent=2),
            user_context=user_context,
        )
    else:
        prompt = (
            "Tu es CashPilot, un copilote financier bienveillant et direct. "
            "Reformule cette décision financière de manière naturelle, chaleureuse et actionnable. "
            "Utilise des emojis. Sois concis (max 5-6 lignes). "
            "IMPORTANT: Ne change PAS la décision. Si c'est NO, dis non. Si c'est YES, dis oui.\n\n"
            f"Contexte utilisateur : {user_context}\n\n"
            f"Profil financier : {financial_profile}\n\n"
            f"Décision brute :\n{json.dumps(decision_data, ensure_ascii=False, indent=2)}"
        )

    t0 = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=get_model_name(),
            messages=[{"role": "system", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
            timeout=15.0,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        result = response.choices[0].message.content or _format_raw_decision(decision_data)
        logger.info(f"[LLM] reformulation: {elapsed_ms}ms, decision={decision_data.get('decision_status', '?')}")
        return result
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(f"[LLM] reformulation failed: {type(e).__name__}: {e} ({elapsed_ms}ms)")
        return _format_raw_decision(decision_data)


async def generate_follow_up_questions(
    missing_info: list[str],
    context: str = "",
) -> str:
    """Use LLM to formulate natural follow-up questions.
    NEVER raises — returns formatted list on error.
    """
    client = get_openai_client()
    if not client or not missing_info:
        return "\n".join(f"❓ {q}" for q in missing_info)

    prompt_template = _load_prompt("ask_missing_info_prompt.txt")
    if prompt_template and "{missing_info}" in prompt_template:
        prompt = prompt_template.format(
            missing_info=json.dumps(missing_info, ensure_ascii=False),
            purchase_context=context,
        )
    else:
        prompt = (
            "Tu es CashPilot. Pose ces questions de manière naturelle et bienveillante, "
            "comme un ami qui s'y connaît en finance. Une question par ligne, avec un emoji.\n\n"
            f"Infos manquantes : {json.dumps(missing_info, ensure_ascii=False)}\n"
            f"Contexte : {context}"
        )

    t0 = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=get_model_name(),
            messages=[{"role": "system", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
            timeout=10.0,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(f"[LLM] follow-up questions: {elapsed_ms}ms")
        return response.choices[0].message.content or "\n".join(
            f"❓ {q}" for q in missing_info
        )
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(f"[LLM] follow-up generation failed: {type(e).__name__}: {e} ({elapsed_ms}ms)")
        return "\n".join(f"❓ {q}" for q in missing_info)


async def parse_natural_amount(text: str) -> float | None:
    """Use LLM to extract a monetary amount from natural language.

    Handles: "je gagne 1500€ de stage", "environ 2000", "1.5k", "0", "aucun"
    NEVER raises — returns _simple_amount_parse fallback on error.
    """
    client = get_openai_client()
    if not client:
        logger.info("[LLM] No client — using simple amount parser")
        return _simple_amount_parse(text)

    t0 = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=get_model_name(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extrais le montant en euros de ce message. "
                        "Réponds UNIQUEMENT avec un nombre (ex: 1500.00). "
                        "Si le message dit 0, aucun, rien, pas de, réponds 0. "
                        "Si aucun montant trouvé, réponds null."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.0,
            max_tokens=20,
            timeout=5.0,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        content = (response.choices[0].message.content or "").strip()
        logger.debug(f"[LLM] amount extraction: {text!r} → {content!r} ({elapsed_ms}ms)")

        if content.lower() in ("null", "none", ""):
            return None
        return max(0.0, float(content.replace(",", ".").replace("€", "")))
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(f"[LLM] amount parsing failed: {type(e).__name__}: {e} ({elapsed_ms}ms) — using fallback")
        return _simple_amount_parse(text)


async def parse_natural_choice(
    text: str,
    options: dict[str, list[str]],
    default: str = "",
) -> str:
    """Use LLM to match a natural language answer to predefined options.
    NEVER raises — returns keyword-based fallback on error.
    """
    client = get_openai_client()
    if not client:
        return _simple_choice_parse(text, options, default)

    options_desc = "\n".join(
        f"- \"{key}\": {', '.join(vals)}" for key, vals in options.items()
    )

    t0 = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=get_model_name(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"L'utilisateur doit choisir parmi ces options :\n{options_desc}\n\n"
                        "Réponds UNIQUEMENT avec la clé de l'option qui correspond le mieux. "
                        f"Si aucune ne correspond, réponds \"{default}\"."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.0,
            max_tokens=20,
            timeout=5.0,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        result = (response.choices[0].message.content or default).strip().strip('"')
        logger.debug(f"[LLM] choice: {text!r} → {result!r} ({elapsed_ms}ms)")
        return result if result in options else default
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(f"[LLM] choice parsing failed: {type(e).__name__}: {e} ({elapsed_ms}ms) — using fallback")
        return _simple_choice_parse(text, options, default)


# ── Fallbacks ────────────────────────────────────────────

def _default_response(intent: str) -> str:
    """Default response when LLM is unavailable."""
    if intent == "greeting":
        return (
            "👋 Salut ! Je suis CashPilot, ton copilote financier.\n\n"
            "Tu peux :\n"
            "• Noter une dépense : \"25 resto\"\n"
            "• Demander un avis : \"je veux acheter un iPhone à 1200€\"\n"
            "• Voir ton résumé : /summary"
        )
    return (
        "🤔 Je n'ai pas bien compris. Tu peux :\n"
        "• Noter une dépense : \"25 resto\"\n"
        "• Demander un avis : /canibuy\n"
        "• Voir ton résumé : /summary"
    )


def _format_raw_decision(decision_data: dict) -> str:
    """Format a raw decision when LLM reformulation fails."""
    status = decision_data.get("decision_status", "?")
    item = decision_data.get("item_name", "?")
    price = decision_data.get("price", "?")
    reason = decision_data.get("main_reason", "")
    risk = decision_data.get("risk_score", "?")

    emoji_map = {"YES": "✅", "NO": "❌", "WAIT": "⏳", "CONDITIONAL": "⚠️"}
    emoji = emoji_map.get(status, "❓")

    lines = [
        f"{emoji} *{status}* — {item} ({price}€)",
        f"📊 Risque : {risk}/100",
    ]
    if reason:
        lines.append(f"💡 {reason}")
    return "\n".join(lines)


def _simple_amount_parse(text: str) -> float | None:
    """Simple regex-based amount extraction fallback."""
    import re
    cleaned = text.strip().replace("€", "").replace(",", ".")
    match = re.search(r"(\d+(?:\.\d{1,2})?)", cleaned)
    if match:
        return max(0.0, float(match.group(1)))
    if any(w in cleaned.lower() for w in ("0", "aucun", "rien", "pas de", "non")):
        return 0.0
    return None


def _simple_choice_parse(
    text: str, options: dict[str, list[str]], default: str
) -> str:
    """Simple keyword-based choice matching fallback."""
    text_lower = text.lower().strip()
    for key, keywords in options.items():
        for kw in keywords:
            if kw in text_lower:
                return key
    return default
