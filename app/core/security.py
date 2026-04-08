"""Security utilities — API key validation, webhook signature verification."""

import hashlib
import hmac
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """Validate the API key from request header."""
    settings = get_settings()
    if not settings.API_KEY:
        return "no-auth"
    if api_key and hmac.compare_digest(api_key, settings.API_KEY):
        return api_key
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid or missing API key",
    )


def verify_telegram_secret(token: str) -> bool:
    """Verify a Telegram webhook secret token."""
    settings = get_settings()
    if not settings.TELEGRAM_WEBHOOK_SECRET:
        return True
    return hmac.compare_digest(token, settings.TELEGRAM_WEBHOOK_SECRET)
