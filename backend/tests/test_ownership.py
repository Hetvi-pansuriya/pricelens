import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from models import User, Company, AnalysisSession, Report
from routers.companies import get_company_or_404, verify_company_ownership
from routers.analysis import get_report


@pytest.mark.asyncio
async def test_get_company_denied_for_different_user():
    user1 = User(id=uuid.uuid4(), email="user1@example.com")
    user2 = User(id=uuid.uuid4(), email="user2@example.com")
    company_id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_result = MagicMock()
    # Company exists but belongs to user1, user2 requests it
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc:
        await get_company_or_404(company_id, user2, mock_db)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Company not found"


@pytest.mark.asyncio
async def test_verify_company_ownership_denied():
    user1 = User(id=uuid.uuid4(), email="user1@example.com")
    company_id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc:
        await verify_company_ownership(company_id, user1, mock_db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_report_denied_for_non_owner():
    user_owner = User(id=uuid.uuid4(), email="owner@example.com")
    user_attacker = User(id=uuid.uuid4(), email="attacker@example.com")
    session_id = uuid.uuid4()

    company = Company(id=uuid.uuid4(), user_id=user_owner.id, name="TestCo", industry="saas")
    session = AnalysisSession(id=session_id, company_id=company.id, company=company)
    report = Report(id=uuid.uuid4(), session_id=session_id, json_report={}, session=session)

    mock_db = AsyncMock()
    mock_report_res = MagicMock()
    mock_report_res.scalar_one_or_none.return_value = report

    mock_sess_res = MagicMock()
    mock_sess_res.scalar_one_or_none.return_value = session

    mock_db.execute.side_effect = [mock_report_res, mock_sess_res]

    with pytest.raises(HTTPException) as exc:
        await get_report(session_id=session_id, current_user=user_attacker, db=mock_db)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Access denied"
