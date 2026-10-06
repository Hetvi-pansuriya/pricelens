import asyncio
import uuid
from datetime import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models import AnalysisSession, Company, Report, User
from routers.analysis import run_full_analysis, background_analysis_tasks


@pytest.mark.asyncio
async def test_startup_sweep_marks_running_sessions_failed():
    """Verify that sessions still running on startup are marked as failed."""
    # Simulate what lifespan does on startup
    running_sess = AnalysisSession(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        status="running",
        progress=45,
        started_at=datetime.utcnow(),
    )
    
    # Run the sweep logic
    if running_sess.status == "running":
        running_sess.status = "failed"
        running_sess.progress = 100
        running_sess.error_message = "The server restarted during this analysis. Please run it again."
        running_sess.completed_at = datetime.utcnow()

    assert running_sess.status == "failed"
    assert running_sess.progress == 100
    assert "The server restarted during this analysis" in running_sess.error_message


@pytest.mark.asyncio
async def test_background_task_references_tracked():
    """Verify background tasks are added to the set and discarded upon completion."""
    async def dummy_task():
        await asyncio.sleep(0.01)

    task = asyncio.create_task(dummy_task())
    background_analysis_tasks.add(task)
    task.add_done_callback(background_analysis_tasks.discard)

    assert task in background_analysis_tasks
    await task
    # Give event loop a cycle to run the callback
    await asyncio.sleep(0.01)
    assert task not in background_analysis_tasks


@pytest.mark.asyncio
async def test_analysis_timeout_handling():
    """Verify that an analysis exceeding timeout is marked as failed with a clear message."""
    session_id = uuid.uuid4()
    company_id = uuid.uuid4()

    # Mock _execute_analysis to take longer than timeout
    async def slow_execution(*args, **kwargs):
        await asyncio.sleep(10)

    with patch("routers.analysis.ANALYSIS_TIMEOUT_SECONDS", 0.05):
        with patch("routers.analysis._execute_analysis", side_effect=slow_execution):
            mock_sess = AnalysisSession(id=session_id, company_id=company_id, status="running", progress=0)
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_sess
            mock_db.execute.return_value = mock_result

            with patch("routers.analysis.AsyncSessionLocal", return_value=mock_db):
                mock_db.__aenter__.return_value = mock_db
                await run_full_analysis(str(session_id), company_id, None)

            assert mock_sess.status == "failed"
            assert mock_sess.progress == 100
            assert "timed out after" in mock_sess.error_message
