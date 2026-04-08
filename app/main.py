"""CashPilot — FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger
from app.api.routes import health, users, accounts, transactions, goals, decisions, telegram_webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown events."""
    setup_logging()
    logger = get_logger("main")
    settings = get_settings()
    logger.info(f"CashPilot starting — env={settings.APP_ENV}")

    # Set up Telegram webhook if configured
    if settings.TELEGRAM_WEBHOOK_URL and settings.TELEGRAM_BOT_TOKEN:
        import httpx
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook"
        payload = {
            "url": f"{settings.TELEGRAM_WEBHOOK_URL}",
            "secret_token": settings.TELEGRAM_WEBHOOK_SECRET,
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload)
                logger.info(f"Webhook setup: {resp.json()}")
        except Exception as e:
            logger.error(f"Webhook setup failed: {e}")

    yield

    logger.info("CashPilot shutting down")


app = FastAPI(
    title="CashPilot",
    description="Copilote financier conversationnel — API",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Register routes ──────────────────────────────────────
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(users.router, prefix="/api/v1", tags=["users"])
app.include_router(accounts.router, prefix="/api/v1", tags=["accounts"])
app.include_router(transactions.router, prefix="/api/v1", tags=["transactions"])
app.include_router(goals.router, prefix="/api/v1", tags=["goals"])
app.include_router(decisions.router, prefix="/api/v1", tags=["decisions"])
app.include_router(telegram_webhook.router, prefix="/api/v1", tags=["telegram"])


@app.get("/")
async def root():
    return {"service": "cashpilot", "docs": "/docs"}
