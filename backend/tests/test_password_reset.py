import hashlib
import uuid
from datetime import datetime, timedelta
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import Request

from routers.auth import forgot_password, reset_password
from schemas import LoginRequest, ResetPasswordBody
from models import User, PasswordResetToken


@pytest.mark.asyncio
async def test_forgot_password_uniform_response_for_nonexistent_email():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    req = MagicMock(spec=Request)
    res = await forgot_password(request=req, body=LoginRequest(email="nobody@example.com", password=""), db=mock_db)
    assert res == {"message": "If this email exists, a reset link has been sent."}


@pytest.mark.asyncio
async def test_forgot_password_stores_hashed_token():
    mock_db = AsyncMock()
    fake_user = User(id=uuid.uuid4(), email="user@example.com", password_hash="hash")
    
    mock_result_user = MagicMock()
    mock_result_user.scalar_one_or_none.return_value = fake_user
    mock_result_tokens = MagicMock()
    mock_result_tokens.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [mock_result_user, mock_result_tokens]

    added_objects = []
    mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    req = MagicMock(spec=Request)
    res = await forgot_password(request=req, body=LoginRequest(email="user@example.com", password=""), db=mock_db)
    assert res == {"message": "If this email exists, a reset link has been sent."}
    
    # Verify the stored token in DB is a 64-char hex string (SHA-256)
    assert len(added_objects) == 1
    stored_token = added_objects[0]
    assert isinstance(stored_token, PasswordResetToken)
    assert len(stored_token.token) == 64
    assert all(c in "0123456789abcdef" for c in stored_token.token)
