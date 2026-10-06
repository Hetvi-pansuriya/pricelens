import pytest
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from rate_limiter import (
    limiter,
    custom_rate_limit_exceeded_handler,
    check_login_lockout,
    record_failed_login,
    clear_failed_logins,
    _FAILED_LOGINS,
    get_user_id_key,
)


@pytest.fixture(autouse=True)
def clean_state():
    """Reset limiter and failed logins before each test."""
    _FAILED_LOGINS.clear()
    limiter.reset()
    yield
    _FAILED_LOGINS.clear()
    limiter.reset()


def test_ip_rate_limiting_returns_429_with_message():
    app = FastAPI()
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, custom_rate_limit_exceeded_handler)

    @app.post("/test-limit")
    @limiter.limit("2/minute")
    def endpoint(request: Request):
        return {"status": "ok"}

    client = TestClient(app)
    r1 = client.post("/test-limit")
    assert r1.status_code == 200

    r2 = client.post("/test-limit")
    assert r2.status_code == 200

    r3 = client.post("/test-limit")
    assert r3.status_code == 429
    data = r3.json()
    assert "Rate limit exceeded" in data["detail"]
    assert "Please try again in 1 minute" in data["detail"]


def test_failed_login_lockout_after_5_attempts():
    email = "test@example.com"
    clear_failed_logins(email)

    # 4 failed attempts should not lock out
    for _ in range(4):
        check_login_lockout(email)
        record_failed_login(email)

    assert email in _FAILED_LOGINS
    assert _FAILED_LOGINS[email]["count"] == 4
    assert _FAILED_LOGINS[email]["locked_until"] is None

    # 5th attempt must trigger lockout
    with pytest.raises(HTTPException) as exc:
        record_failed_login(email)
    assert exc.value.status_code == 429
    assert "temporarily locked" in exc.value.detail
    assert "15 minutes" in exc.value.detail

    # Subsequent check_login_lockout should also raise 429
    with pytest.raises(HTTPException) as exc2:
        check_login_lockout(email)
    assert exc2.value.status_code == 429
    assert "temporarily locked" in exc2.value.detail

    # Clearing resets it
    clear_failed_logins(email)
    check_login_lockout(email)  # Should not raise


def test_expired_lockout_clears_automatically():
    email = "expired@example.com"
    _FAILED_LOGINS[email] = {
        "count": 5,
        "locked_until": datetime.utcnow() - timedelta(minutes=1),
    }

    # Should detect expired lock and clear
    check_login_lockout(email)
    assert email not in _FAILED_LOGINS
