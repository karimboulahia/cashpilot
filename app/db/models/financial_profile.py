"""Financial profile model — stores user's financial situation for decision engine."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class FinancialProfile(Base, TimestampMixin):
    __tablename__ = "financial_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )

    # Income
    monthly_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    income_type: Mapped[str] = mapped_column(
        String(50), default="stable"
    )  # stable / variable / internship / freelance / none
    income_end_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Expenses
    monthly_fixed_charges: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    # Savings & Debt
    available_savings: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total_debt: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    # Living situation
    housing_situation: Mapped[str] = mapped_column(
        String(50), default="alone"
    )  # alone / family / shared

    # Safety net
    safety_net_months: Mapped[int] = mapped_column(Integer, default=3)

    # Goals & risk
    main_goal: Mapped[str] = mapped_column(
        String(100), default="stability"
    )  # stability / car / travel / investment / pay_debt / other
    risk_tolerance: Mapped[str] = mapped_column(
        String(50), default="balanced"
    )  # prudent / balanced / aggressive

    # Relationship
    user: Mapped["User"] = relationship(back_populates="financial_profile")

    # ── Computed helpers ─────────────────────────────────
    @property
    def monthly_disposable(self) -> Decimal:
        """Monthly income minus fixed charges."""
        return self.monthly_income - self.monthly_fixed_charges

    @property
    def safety_net_target(self) -> Decimal:
        """Target amount for the safety cushion."""
        return self.monthly_fixed_charges * self.safety_net_months

    def __repr__(self) -> str:
        return f"<FinancialProfile user_id={self.user_id} income={self.monthly_income}>"
