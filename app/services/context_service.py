"""Context service — per-user conversation memory backed by DB.

Provides simple get/update/clear operations for multi-turn state,
onboarding step tracking, and recent message history.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.conversation_context import ConversationContext

logger = get_logger("context_service")

MAX_RECENT_MESSAGES = 10


async def get_context(db: AsyncSession, user_id: int) -> ConversationContext:
    """Get or create conversation context for a user."""
    result = await db.execute(
        select(ConversationContext).where(ConversationContext.user_id == user_id)
    )
    ctx = result.scalar_one_or_none()
    if ctx:
        return ctx

    ctx = ConversationContext(user_id=user_id, recent_messages=[], context_data={})
    db.add(ctx)
    await db.flush()
    await db.refresh(ctx)
    return ctx


async def update_context(
    db: AsyncSession,
    user_id: int,
    *,
    last_intent: str | None = None,
    last_item_name: str | None = None,
    last_amount: str | None = None,
    last_topic: str | None = None,
    pending_action: str | None = None,
    onboarding_step: str | None = None,
    extra_data: dict | None = None,
) -> ConversationContext:
    """Update context fields. Only non-None values are updated."""
    ctx = await get_context(db, user_id)

    if last_intent is not None:
        ctx.last_intent = last_intent
    if last_item_name is not None:
        ctx.last_item_name = last_item_name
    if last_amount is not None:
        ctx.last_amount = last_amount
    if last_topic is not None:
        ctx.last_topic = last_topic
    if pending_action is not None:
        ctx.pending_action = pending_action
    if onboarding_step is not None:
        ctx.onboarding_step = onboarding_step
    if extra_data is not None:
        existing = ctx.context_data or {}
        existing.update(extra_data)
        ctx.context_data = existing

    await db.flush()
    return ctx


async def add_message_to_history(
    db: AsyncSession,
    user_id: int,
    role: str,
    content: str,
) -> None:
    """Append a message to the recent conversation history."""
    ctx = await get_context(db, user_id)
    messages = list(ctx.recent_messages or [])
    messages.append({
        "role": role,
        "content": content[:500],  # Truncate long messages
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    # Keep only last N messages
    ctx.recent_messages = messages[-MAX_RECENT_MESSAGES:]
    await db.flush()


async def clear_pending_action(db: AsyncSession, user_id: int) -> None:
    """Clear any pending multi-turn action."""
    ctx = await get_context(db, user_id)
    ctx.pending_action = None
    await db.flush()


def build_context_summary(ctx: ConversationContext) -> str:
    """Build a short text summary of the current context for LLM prompts."""
    parts = []
    if ctx.last_intent:
        parts.append(f"Dernier intent: {ctx.last_intent}")
    if ctx.last_item_name:
        parts.append(f"Dernier article discuté: {ctx.last_item_name}")
    if ctx.last_amount:
        parts.append(f"Dernier montant: {ctx.last_amount}€")
    if ctx.pending_action:
        parts.append(f"Action en attente: {ctx.pending_action}")

    # Last few messages for context
    messages = ctx.recent_messages or []
    if messages:
        recent = messages[-3:]  # Last 3 messages
        msg_lines = [f"  {m['role']}: {m['content'][:100]}" for m in recent]
        parts.append("Messages récents:\n" + "\n".join(msg_lines))

    return "\n".join(parts) if parts else "Aucun contexte précédent."
