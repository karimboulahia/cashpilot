"""AI Parser — LLM-powered natural language understanding for CashPilot.

Replaces the regex-only parser with GPT-4o-mini for robust French NLU.
Falls back to the deterministic parser_service when LLM is unavailable.

The parser ONLY extracts intents and entities.
It NEVER makes financial decisions — that is the decision engine's role.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.core.logging import get_logger
from app.services.llm_service import get_openai_client, get_model_name
from app.services.parser_service import parse_expense

logger = get_logger("ai_parser")

# Load the NLU prompt template once
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "parse_message_prompt.txt"
_NLU_PROMPT_TEMPLATE: str | None = None


def _get_nlu_prompt() -> str:
    """Lazy-load the NLU prompt template."""
    global _NLU_PROMPT_TEMPLATE
    if _NLU_PROMPT_TEMPLATE is None:
        _NLU_PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")
    return _NLU_PROMPT_TEMPLATE


@dataclass
class ParsedMessage:
    """Structured result from parsing a user message."""
    intent: str = "unknown"
    confidence: float = 0.5
    entities: dict = field(default_factory=dict)
    raw_response: dict = field(default_factory=dict)
    used_fallback: bool = False


async def parse_user_message(
    message: str,
    context_summary: str = "",
) -> ParsedMessage:
    """Parse a user message using LLM-powered NLU.

    Args:
        message: The raw user message text.
        context_summary: A summary of conversation context for multi-turn.

    Returns:
        ParsedMessage with intent, confidence, and extracted entities.
        NEVER raises — always returns a valid ParsedMessage.
    """
    logger.info(f"[NLU] input: {message!r}")

    client = get_openai_client()
    if not client:
        logger.warning("[NLU] No OpenAI client — using fallback parser")
        return _fallback_parse(message)

    t0 = time.monotonic()
    try:
        prompt = _get_nlu_prompt().replace("{context}", context_summary or "Aucun contexte.")

        response = await client.chat.completions.create(
            model=get_model_name(),
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": message},
            ],
            temperature=0.1,
            max_tokens=400,
            timeout=10.0,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        content = response.choices[0].message.content or "{}"
        content = content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        result = json.loads(content)

        parsed = ParsedMessage(
            intent=result.get("intent", "unknown"),
            confidence=float(result.get("confidence", 0.5)),
            entities=result.get("entities", {}),
            raw_response=result,
            used_fallback=False,
        )

        logger.info(
            f"[NLU] LLM result: intent={parsed.intent} "
            f"confidence={parsed.confidence:.2f} "
            f"entities={parsed.entities} "
            f"elapsed={elapsed_ms}ms"
        )
        return parsed

    except json.JSONDecodeError as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(
            f"[NLU] Malformed JSON from LLM: {e} "
            f"raw={content!r} elapsed={elapsed_ms}ms — using fallback"
        )
        return _fallback_parse(message)

    except TimeoutError:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(f"[NLU] LLM timeout after {elapsed_ms}ms — using fallback")
        return _fallback_parse(message)

    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(f"[NLU] LLM error: {type(e).__name__}: {e} elapsed={elapsed_ms}ms — using fallback")
        return _fallback_parse(message)


def _fallback_parse(message: str) -> ParsedMessage:
    """Deterministic fallback using keyword matching and parser_service.

    Called when LLM is unavailable, times out, or returns invalid JSON.
    Guarantees a valid ParsedMessage — never raises.

    Order: cancel → correct → purchase → summary → greeting → regex expense → unknown
    Keywords are checked FIRST because regex would match numbers in "corrige 20".
    """
    import re

    logger.info(f"[NLU] Fallback parser for: {message!r}")
    msg = message.lower().strip()

    # ── 1. Cancel keywords (highest priority) ────────────
    cancel_kw = ["annule", "pas ça", "supprime", "cancel", "undo", "delete"]
    for kw in cancel_kw:
        if kw in msg:
            logger.info(f"[NLU] Fallback keyword match: cancel_last ({kw!r})")
            return ParsedMessage(
                intent="cancel_last", confidence=0.8,
                entities={}, used_fallback=True,
            )

    # ── 2. Correction keywords ───────────────────────────
    correct_patterns = [
        r"corrige\s+(\d+[\.,]?\d*)",
        r"non\s+c['\u2019](?:é|e)tait\s+(\d+[\.,]?\d*)",
        r"non\s+pas\s+\d+[\.,]?\d*\s+mais\s+(\d+[\.,]?\d*)",
        r"c['\u2019](?:é|e)(?:tai)?t\s+(\d+[\.,]?\d*)",
    ]
    for pattern in correct_patterns:
        m = re.search(pattern, msg)
        if m:
            amount = float(m.group(1).replace(",", "."))
            logger.info(f"[NLU] Fallback keyword match: correct_last amount={amount}")
            return ParsedMessage(
                intent="correct_last", confidence=0.75,
                entities={"amount": amount}, used_fallback=True,
            )

    # ── 3. Purchase keywords ─────────────────────────────
    purchase_kw = [
        "acheter", "achat", "est-ce que je peux", "puis-je",
        "je veux acheter", "j'aimerais", "budget pour", "canibuy",
        "je peux l'acheter", "c'est raisonnable",
        "buy", "purchase", "can i afford", "can i buy",
    ]
    for kw in purchase_kw:
        if kw in msg:
            logger.info(f"[NLU] Fallback keyword match: ask_purchase ({kw!r})")
            return ParsedMessage(
                intent="ask_purchase", confidence=0.6,
                entities={}, used_fallback=True,
            )

    # ── 4. Summary keywords ──────────────────────────────
    summary_kw = ["résumé", "resume", "summary", "situation", "bilan"]
    for kw in summary_kw:
        if kw in msg:
            logger.info("[NLU] Fallback keyword match: show_summary")
            return ParsedMessage(intent="show_summary", confidence=0.7, used_fallback=True)

    # ── 5. Greeting ──────────────────────────────────────
    greeting_kw = ["bonjour", "salut", "hello", "hi", "hey", "coucou"]
    for kw in greeting_kw:
        if msg.startswith(kw):
            return ParsedMessage(intent="greeting", confidence=0.9, used_fallback=True)

    # ── 6. Regex expense/income parser (last resort) ─────
    try:
        parsed = parse_expense(message)
        if parsed:
            intent = "add_income" if parsed.is_income else "add_expense"
            result = ParsedMessage(
                intent=intent,
                confidence=0.7,
                entities={
                    "amount": parsed.amount,
                    "category": parsed.category,
                    "description": parsed.description,
                },
                used_fallback=True,
            )
            logger.info(f"[NLU] Fallback regex: {result.intent} amount={parsed.amount}")
            return result
    except Exception as e:
        logger.error(f"[NLU] Fallback regex parser error: {e}")

    logger.info("[NLU] Fallback: no match → unknown")
    return ParsedMessage(intent="unknown", confidence=0.3, used_fallback=True)

