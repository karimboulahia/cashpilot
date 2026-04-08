"""Reporting service — financial summary and health assessment."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.services import account_service, transaction_service
from app.services.profile_service import get_or_create_profile


async def get_financial_summary(db: AsyncSession, user: User) -> dict:
    """Generate a complete financial summary for a user."""
    profile = await get_or_create_profile(db, user.id)
    accounts = await account_service.get_user_accounts(db, user.id)
    total_patrimony = await account_service.get_total_patrimony(db, user.id)
    total_liquid = await account_service.get_total_liquid_cash(db, user.id)
    monthly_spending = await transaction_service.get_monthly_spending(db, user.id)
    top_categories = await transaction_service.get_spending_by_category(db, user.id)
    spending_trend = await transaction_service.get_spending_trend(db, user.id)

    safety_target = profile.monthly_fixed_charges * profile.safety_net_months
    safety_current = min(total_liquid, profile.available_savings)

    # Health assessment
    health = _assess_health(
        total_liquid=total_liquid,
        safety_target=safety_target,
        monthly_spending=monthly_spending,
        monthly_income=profile.monthly_income,
        total_debt=profile.total_debt,
        income_type=profile.income_type,
    )

    return {
        "user_name": user.first_name or user.username or "Utilisateur",
        "total_patrimony": str(total_patrimony),
        "total_liquid_cash": str(total_liquid),
        "monthly_income": str(profile.monthly_income),
        "monthly_fixed_charges": str(profile.monthly_fixed_charges),
        "monthly_spending_tracked": str(monthly_spending),
        "safety_net_target": str(safety_target),
        "safety_net_current": str(safety_current),
        "main_goal": profile.main_goal,
        "income_type": profile.income_type,
        "spending_trend": spending_trend,
        "top_categories": [
            {"category": c["category"], "total": str(c["total"])}
            for c in top_categories[:5]
        ],
        "accounts_count": len(accounts),
        "health_status": health,
    }


def _assess_health(
    total_liquid: Decimal,
    safety_target: Decimal,
    monthly_spending: Decimal,
    monthly_income: Decimal,
    total_debt: Decimal,
    income_type: str,
) -> str:
    """Assess overall financial health: fragile / correct / solide."""
    score = 0

    # Safety cushion coverage
    if safety_target > 0:
        ratio = total_liquid / safety_target
        if ratio >= 1.5:
            score += 3
        elif ratio >= 1.0:
            score += 2
        elif ratio >= 0.5:
            score += 1

    # Income stability
    if income_type == "stable":
        score += 2
    elif income_type in ("variable", "freelance"):
        score += 1

    # Spending vs income
    if monthly_income > 0:
        spending_ratio = monthly_spending / monthly_income
        if spending_ratio < Decimal("0.6"):
            score += 2
        elif spending_ratio < Decimal("0.8"):
            score += 1

    # Debt
    if total_debt == 0:
        score += 1

    if score >= 6:
        return "solide"
    elif score >= 3:
        return "correct"
    return "fragile"


def format_summary_message(summary: dict) -> str:
    """Format a financial summary as a readable Telegram message."""
    health_emoji = {"fragile": "🔴", "correct": "🟡", "solide": "🟢"}.get(
        summary["health_status"], "⚪"
    )

    lines = [
        f"📊 *Résumé financier — {summary['user_name']}*",
        "",
        f"💰 Patrimoine total : {summary['total_patrimony']}€",
        f"💵 Cash disponible : {summary['total_liquid_cash']}€",
        f"📥 Revenu mensuel : {summary['monthly_income']}€ ({summary['income_type']})",
        f"📤 Charges fixes : {summary['monthly_fixed_charges']}€/mois",
        f"🛒 Dépenses trackées (30j) : {summary['monthly_spending_tracked']}€",
        "",
        f"🛡️ Matelas cible : {summary['safety_net_target']}€",
        f"🛡️ Matelas actuel : {summary['safety_net_current']}€",
        f"🎯 Objectif : {summary['main_goal']}",
        "",
        f"{health_emoji} État global : *{summary['health_status'].upper()}*",
    ]

    if summary["top_categories"]:
        lines.append("")
        lines.append("📋 *Top dépenses du mois :*")
        for cat in summary["top_categories"]:
            lines.append(f"  • {cat['category']} : {cat['total']}€")

    return "\n".join(lines)
