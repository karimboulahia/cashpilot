"""User model."""

from sqlalchemy import BigInteger, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str] = mapped_column(String(10), default="fr")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    financial_profile: Mapped["FinancialProfile"] = relationship(
        back_populates="user", uselist=False, lazy="selectin"
    )
    accounts: Mapped[list["Account"]] = relationship(
        back_populates="user", lazy="selectin"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="user", lazy="selectin"
    )
    goals: Mapped[list["Goal"]] = relationship(
        back_populates="user", lazy="selectin"
    )
    purchase_decisions: Mapped[list["PurchaseDecision"]] = relationship(
        back_populates="user", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} tg={self.telegram_id}>"
