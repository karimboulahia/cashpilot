"""Purchase decision model — stores decision engine results."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class PurchaseDecision(Base, TimestampMixin):
    __tablename__ = "purchase_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # ── Purchase request ─────────────────────────────────
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    item_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_type: Mapped[str] = mapped_column(String(50), default="cash")  # cash / installments
    essentiality: Mapped[str] = mapped_column(
        String(50), default="comfort"
    )  # essential / useful / comfort / impulse
    recurring_cost_estimate: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0")
    )

    # ── Decision output ──────────────────────────────────
    decision_status: Mapped[str] = mapped_column(String(20), nullable=False)  # YES / NO / WAIT / CONDITIONAL
    confidence_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    recommended_max_budget: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    main_reason: Mapped[str] = mapped_column(Text, default="")
    risk_factors: Mapped[dict] = mapped_column(JSON, default=list)
    positives: Mapped[dict] = mapped_column(JSON, default=list)
    explanation_short: Mapped[str] = mapped_column(Text, default="")
    explanation_detailed: Mapped[str] = mapped_column(Text, default="")
    alternative_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship
    user: Mapped["User"] = relationship(back_populates="purchase_decisions")

    def __repr__(self) -> str:
        return f"<PurchaseDecision id={self.id} item={self.item_name} status={self.decision_status}>"
