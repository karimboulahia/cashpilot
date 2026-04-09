"""Conversation context model — per-user memory for multi-turn interactions."""

from sqlalchemy import ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ConversationContext(Base, TimestampMixin):
    __tablename__ = "conversation_contexts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )

    # Last interaction state
    last_intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_amount: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_topic: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Pending multi-turn action (e.g., waiting for price after item name)
    pending_action: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Onboarding step (replaces in-memory dict)
    onboarding_step: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Recent conversation history (last N messages as JSON list)
    recent_messages: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Flexible context data (any extra state)
    context_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationship
    user: Mapped["User"] = relationship()

    def __repr__(self) -> str:
        return f"<ConversationContext user_id={self.user_id} intent={self.last_intent}>"
