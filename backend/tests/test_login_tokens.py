import uuid
from datetime import datetime, timedelta
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from routers.auth import get_current_user, create_access_token
from models import User
from routers.analysis import _PROGRESS_TICKETS, _cleanup_expired_tickets


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_credentials():
    mock_db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await get_current_user(credentials=None, db=mock_db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_accepts_valid_bearer_token():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    fake_user = User(id=user_id, email="test@example.com", password_hash="hash")
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_user
    mock_db.execute.return_value = mock_result

    user = await get_current_user(credentials=credentials, db=mock_db)
    assert user.id == user_id


def test_progress_ticket_storage_and_expiry():
    _PROGRESS_TICKETS.clear()
    ticket_valid = "valid_ticket_123"
    ticket_expired = "expired_ticket_456"

    _PROGRESS_TICKETS[ticket_valid] = {
        "user_id": "u1",
        "session_id": "s1",
        "expires_at": datetime.utcnow() + timedelta(seconds=60),
    }
    _PROGRESS_TICKETS[ticket_expired] = {
        "user_id": "u1",
        "session_id": "s1",
        "expires_at": datetime.utcnow() - timedelta(seconds=5),
    }

    _cleanup_expired_tickets()
    assert ticket_valid in _PROGRESS_TICKETS
    assert ticket_expired not in _PROGRESS_TICKETS

    # One-time consumption
    popped = _PROGRESS_TICKETS.pop(ticket_valid, None)
    assert popped is not None
    assert ticket_valid not in _PROGRESS_TICKETS
