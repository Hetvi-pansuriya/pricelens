"""
rate_limiter.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: Rate limiting and brute-force protection for PriceLens endpoints.

NOTE: All in-memory rate limits and lockouts are stored in-memory per server process.

DEFAULTS:
- login and signup: 10 requests per minute per IP
- forgot-password: 5 requests per hour per IP
- login account lockout: locks an email for 15 minutes after 5 consecutive failed attempts
- starting an analysis: ANALYSIS_DAILY_LIMIT per user per day (env var, default 5)
- competitor create/scrape: 20 requests per hour per user
─────────────────────────────────────────────────────────────────────────────
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from jose import jwt

# Rate limiter instance using client IP by default
limiter = Limiter(key_func=get_remote_address)

# In-memory store for tracking failed login attempts per email
# Key: normalized email (lowercased)
# Value: {"count": int, "locked_until": datetime | None}
_FAILED_LOGINS: Dict[str, Dict[str, Any]] = {}
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def get_user_id_key(request: Request) -> str:
    """Extract authenticated user ID from Authorization Bearer token, falling back to IP."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        jwt_secret = os.getenv("JWT_SECRET", "")
        algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        if jwt_secret:
            try:
                payload = jwt.decode(token, jwt_secret, algorithms=[algorithm])
                user_id = payload.get("sub")
                if user_id:
                    return f"user:{user_id}"
            except Exception:
                pass
    return get_remote_address(request)


def get_analysis_daily_limit() -> str:
    """Return the daily analysis limit string (e.g. '5/day')."""
    limit_val = os.getenv("ANALYSIS_DAILY_LIMIT", "5").strip()
    return f"{limit_val}/day"


def get_setup_import_daily_limit() -> str:
    """Return the daily setup import limit string (e.g. '20/day')."""
    limit_val = os.getenv("SETUP_IMPORT_DAILY_LIMIT", "20").strip()
    return f"{limit_val}/day"


def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom HTTP 429 response handler returning plain-English explanation."""
    detail_str = str(exc.detail) if exc.detail else "too many requests"
    
    # Format message indicating when they can retry
    if "minute" in detail_str:
        retry_msg = "Please try again in 1 minute."
    elif "hour" in detail_str:
        retry_msg = "Please try again in 1 hour."
    elif "day" in detail_str:
        retry_msg = "Please try again tomorrow."
    else:
        retry_msg = "Please try again later."

    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": f"Rate limit exceeded ({detail_str}). {retry_msg}"},
    )


def check_login_lockout(email: str) -> None:
    """Check if an email is currently locked out due to excessive failed login attempts."""
    norm_email = email.strip().lower()
    entry = _FAILED_LOGINS.get(norm_email)
    if not entry:
        return

    locked_until: Optional[datetime] = entry.get("locked_until")
    if locked_until:
        now = datetime.utcnow()
        if now < locked_until:
            remaining_seconds = int((locked_until - now).total_seconds())
            remaining_minutes = max(1, (remaining_seconds + 59) // 60)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"This account is temporarily locked due to {MAX_FAILED_LOGIN_ATTEMPTS} failed login attempts. "
                    f"Please try again in {remaining_minutes} minute{'s' if remaining_minutes != 1 else ''}."
                ),
                headers={"Retry-After": str(remaining_seconds)},
            )
        else:
            # Lockout period expired; reset state
            _FAILED_LOGINS.pop(norm_email, None)


def record_failed_login(email: str) -> None:
    """Increment failed login attempt count and trigger 15-minute lockout if threshold is reached."""
    norm_email = email.strip().lower()
    entry = _FAILED_LOGINS.get(norm_email, {"count": 0, "locked_until": None})
    entry["count"] += 1

    if entry["count"] >= MAX_FAILED_LOGIN_ATTEMPTS:
        entry["locked_until"] = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
        _FAILED_LOGINS[norm_email] = entry
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"This account is temporarily locked due to {MAX_FAILED_LOGIN_ATTEMPTS} failed login attempts. "
                f"Please try again in {LOCKOUT_MINUTES} minutes."
            ),
            headers={"Retry-After": str(LOCKOUT_MINUTES * 60)},
        )

    _FAILED_LOGINS[norm_email] = entry


def clear_failed_logins(email: str) -> None:
    """Clear failed login attempt history upon successful authentication."""
    norm_email = email.strip().lower()
    _FAILED_LOGINS.pop(norm_email, None)
