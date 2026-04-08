"""Goal model — user financial objectives."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Goal(Base, TimestampMixin):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    deadline_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)  # 1 = highest
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationship
    user: Mapped["User"] = relationship(back_populates="goals")

    @property
    def remaining(self) -> Decimal:
        return self.target_amount - self.current_amount

    @property
    def progress_pct(self) -> float:
        if self.target_amount == 0:
            return 100.0
        return float(self.current_amount / self.target_amount * 100)

    def __repr__(self) -> str:
        return f"<Goal id={self.id} name={self.name} progress={self.progress_pct:.0f}%>"
