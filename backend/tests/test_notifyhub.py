"""
test_notifyhub.py
─────────────────────────────────────────────────────────────────────────────
Comprehensive unit and integration tests for NotifyHub report email dispatch.
Mocks all HTTP calls (no real network usage).
"""

import asyncio
import base64
import os
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from notifyhub_client import (
    send_report_email,
    _format_current_mrr,
    _format_period,
    _truncate_headline,
    _clean_and_format_step,
    _format_expected_change,
)


@pytest.fixture(autouse=True)
def clean_env():
    """Ensure a clean test environment for NotifyHub settings."""
    old_env = os.environ.copy()
    os.environ["REPORT_VIA_NOTIFYHUB"] = "true"
    os.environ["NOTIFYHUB_URL"] = "https://notifyhub.test"
    os.environ["NOTIFYHUB_API_KEY"] = "test-secret-key-12345"
    os.environ["FRONTEND_URL"] = "https://pricelens.io"
    os.environ["NOTIFYHUB_TIMEOUT_SECONDS"] = "5"
    os.environ["NOTIFYHUB_MAX_ATTACHMENT_MB"] = "5"
    yield
    os.environ.clear()
    os.environ.update(old_env)


@pytest.mark.asyncio
async def test_flag_off_runs_existing_code_and_notifyhub_never_called():
    """When REPORT_VIA_NOTIFYHUB is false or missing credentials, NotifyHub is never called."""
    os.environ["REPORT_VIA_NOTIFYHUB"] = "false"

    with patch("notifyhub_client.send_analysis_complete_email", new_callable=AsyncMock) as mock_old, \
         patch("httpx.AsyncClient.post") as mock_post:
        success = await send_report_email(
            to_email="founder@saas.com",
            company_name="CloudHR",
            company_id="c-123",
            session_id="s-456",
            current_mrr=10000,
            recommended_increase="+15%",
        )

        assert success is True
        mock_post.assert_not_called()
        mock_old.assert_awaited_once()


@pytest.mark.asyncio
async def test_flag_on_sends_valid_payload_and_base64_pdf(tmp_path):
    """When flag is enabled, sends correct payload format and base64 PDF attachment."""
    pdf_file = tmp_path / "pricing-report-s-456.pdf"
    pdf_content = b"%PDF-1.4 test pdf content for pricelens"
    pdf_file.write_bytes(pdf_content)

    full_report = {
        "generated_at": "2026-10-15T14:30:00Z",
        "module1_revenue": {
            "current_mrr": 31243.0,
            "currency_symbol": "$",
        },
        "module4_recommendations": {
            "executive_summary": "Your pricing model is underpriced for mid-market customers. Realignment will capture higher margins.",
            "strategies": [
                {
                    "name": "Tier realignment",
                    "predicted_mrr_change_pct": 14,
                    "implementation_steps": [
                        "1. Move data export to Growth tier",
                        "2. Move API access to Enterprise tier",
                        "3. Raise Growth pricing by 15%",
                    ],
                }
            ],
        },
    }

    mock_resp = MagicMock(status_code=202)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        success = await send_report_email(
            to_email="founder@saas.com",
            company_name="CloudHR Pro",
            company_id="c-123",
            session_id="s-456",
            pdf_path=str(pdf_file),
            full_report=full_report,
            currency="USD",
            current_mrr=31243.0,
            recommended_increase="+14%",
            idempotency_key="analysis-s-456-report",
        )

        assert success is True
        mock_post.assert_awaited_once()
        _, kwargs = mock_post.call_args

        # Headers check
        headers = kwargs["headers"]
        assert headers["X-API-Key"] == "test-secret-key-12345"
        assert headers["Content-Type"] == "application/json"
        assert headers["Idempotency-Key"] == "analysis-s-456-report"

        # Payload check
        payload = kwargs["json"]
        assert payload["event_type"] == "analysis_report"
        assert payload["email"] == "founder@saas.com"

        data = payload["data"]
        assert data["app_name"] == "PriceLens"
        assert data["name"] == "there"
        assert data["company_name"] == "CloudHR Pro"
        assert data["report_title"] == "Pricing Analysis Report"
        assert data["period"] == "October 2026"
        assert data["headline"] == "Your pricing model is underpriced for mid-market customers. Realignment will capture higher margins."
        assert data["current_mrr"] == "$31,243"
        assert data["top_strategy"] == "Tier realignment"
        assert data["expected_change"] == "+14%"
        assert data["change_low"] == ""
        assert data["change_high"] == ""
        assert data["step_1"] == "1. Move data export to Growth tier"
        assert data["step_2"] == "2. Move API access to Enterprise tier"
        assert data["step_3"] == "3. Raise Growth pricing by 15%"
        assert data["data_basis"] == "industry benchmarks and AI estimates, not your own customer survey"
        assert data["attachment_note"] == "The full report is attached to this email as a PDF."
        assert data["report_url"] == "https://pricelens.io/reports/s-456"

        # Attachment check
        attachments = payload["attachments"]
        assert len(attachments) == 1
        att = attachments[0]
        assert att["filename"] == "pricelens-report-cloudhr-pro.pdf"
        assert att["content_type"] == "application/pdf"
        assert att["content_base64"] == base64.b64encode(pdf_content).decode("ascii")


def test_formatting_values_and_decision_rules():
    """Verify specific value formatting rules: currencies, dates, steps, and headlines."""
    # 1. MRR formatting
    assert _format_current_mrr(31243, "USD", "$") == "$31,243"
    assert _format_current_mrr(31243.0, "USD", "$") == "$31,243"
    assert _format_current_mrr(31243.5, "USD", "$") == "$31,243.50"
    assert _format_current_mrr(12000, "EUR", "€") == "€12,000"
    assert _format_current_mrr(50000, "INR", "₹") == "₹50,000"

    # 2. Period formatting (independent of server locale)
    assert _format_period("2026-10-09T18:00:00") == "October 2026"
    assert _format_period("2025-01-15") == "January 2025"

    # 3. Expected change formatting
    assert _format_expected_change(8) == "+8%"
    assert _format_expected_change(-3) == "-3%"
    assert _format_expected_change("+12%") == "+12%"

    # 4. Step formatting: strips bullets/numbering and prepends correct number
    assert _clean_and_format_step("• First bullet action", 1) == "1. First bullet action"
    assert _clean_and_format_step("2) Second item", 2) == "2. Second item"
    assert _clean_and_format_step("3. Third item", 3) == "3. Third item"
    assert _clean_and_format_step("", 1) == ""
    assert _clean_and_format_step(None, 2) == ""

    # 5. Headline truncation: cut at last full sentence, or last word
    long_sentences = ("This is sentence one. " * 15) + ("This is sentence two. " * 15)
    truncated = _truncate_headline(long_sentences, max_chars=100)
    assert len(truncated) <= 100
    assert truncated.endswith(".")

    long_single_sentence = "Word " * 60  # no period
    truncated_words = _truncate_headline(long_single_sentence, max_chars=50)
    assert len(truncated_words) <= 50
    assert not truncated_words.endswith(" ")
    assert not truncated_words.endswith("Wor")


@pytest.mark.asyncio
async def test_fewer_than_3_steps_sends_empty_strings():
    """If strategy has fewer than 3 steps, missing steps are sent as empty string."""
    full_report = {
        "module4_recommendations": {
            "strategies": [
                {
                    "name": "One Step Plan",
                    "predicted_mrr_change_pct": 10,
                    "implementation_steps": ["Only one step defined"],
                }
            ]
        }
    }
    mock_resp = MagicMock(status_code=200)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        await send_report_email(
            to_email="user@test.com",
            company_name="SingleStepCo",
            company_id="c-1",
            session_id="s-1",
            full_report=full_report,
        )

        _, kwargs = mock_post.call_args
        data = kwargs["json"]["data"]
        assert data["step_1"] == "1. Only one step defined"
        assert data["step_2"] == ""
        assert data["step_3"] == ""


@pytest.mark.asyncio
async def test_manual_send_unique_idempotency_key_preserved_across_retries():
    """Manual send uses analysis-<id>-report-manual-<uuid> and stays identical during retries."""
    manual_uuid = uuid.uuid4()
    manual_key = f"analysis-s-99-report-manual-{manual_uuid}"

    attempts_keys = []

    async def mock_post_handler(url, json=None, headers=None):
        attempts_keys.append(headers.get("Idempotency-Key"))
        if len(attempts_keys) < 2:
            raise httpx.ConnectError("Network dropped")
        return MagicMock(status_code=200)

    with patch("httpx.AsyncClient.post", side_effect=mock_post_handler), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        success = await send_report_email(
            to_email="user@test.com",
            company_name="ManualCo",
            company_id="c-99",
            session_id="s-99",
            idempotency_key=manual_key,
        )

        assert success is True
        assert len(attempts_keys) == 2
        assert attempts_keys[0] == manual_key
        assert attempts_keys[1] == manual_key


@pytest.mark.asyncio
async def test_pdf_over_limit_omits_attachment(tmp_path):
    """If PDF exceeds NOTIFYHUB_MAX_ATTACHMENT_MB, no attachment is sent and note explains size."""
    os.environ["NOTIFYHUB_MAX_ATTACHMENT_MB"] = "0.001"  # ~1 KB limit

    pdf_file = tmp_path / "large.pdf"
    pdf_file.write_bytes(b"A" * 5000)  # 5 KB

    mock_resp = MagicMock(status_code=200)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        await send_report_email(
            to_email="user@test.com",
            company_name="BigPDFCo",
            company_id="c-2",
            session_id="s-2",
            pdf_path=str(pdf_file),
        )

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["attachments"] == []
        assert payload["data"]["attachment_note"] == "The report was too large to attach, please open it using the link below."


@pytest.mark.asyncio
async def test_missing_or_unreadable_pdf_handles_gracefully():
    """Missing or unreadable PDF sends no attachment and sets in-app note without crashing."""
    mock_resp = MagicMock(status_code=200)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        success = await send_report_email(
            to_email="user@test.com",
            company_name="MissingPDFCo",
            company_id="c-3",
            session_id="s-3",
            pdf_path="/path/does/not/exist/at/all.pdf",
        )

        assert success is True
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["attachments"] == []
        assert payload["data"]["attachment_note"] == "The report is available in the app, please open it using the link below."


@pytest.mark.asyncio
async def test_empty_report_url_when_frontend_url_unset():
    """When FRONTEND_URL is unset, report_url is empty string."""
    os.environ.pop("FRONTEND_URL", None)

    mock_resp = MagicMock(status_code=200)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        await send_report_email(
            to_email="user@test.com",
            company_name="NoFrontendCo",
            company_id="c-4",
            session_id="s-4",
        )

        _, kwargs = mock_post.call_args
        assert kwargs["json"]["data"]["report_url"] == ""


@pytest.mark.asyncio
async def test_status_200_and_202_count_as_success():
    """Both 200 and 202 are recognized as successful sends."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=MagicMock(status_code=200)):
        assert await send_report_email("u@test.com", "Co", "c", "s") is True

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=MagicMock(status_code=202)):
        assert await send_report_email("u@test.com", "Co", "c", "s") is True


@pytest.mark.asyncio
async def test_connection_error_retries_3_times_and_falls_back():
    """Connection errors retry up to 2 times (total 3 attempts) before falling back to old sender."""
    call_count = 0

    async def failing_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("Service down")

    with patch("httpx.AsyncClient.post", side_effect=failing_post), \
         patch("notifyhub_client.send_analysis_complete_email", new_callable=AsyncMock) as mock_fallback, \
         patch("asyncio.sleep", new_callable=AsyncMock):

        await send_report_email("u@test.com", "Co", "c", "s")

        assert call_count == 3
        mock_fallback.assert_awaited_once()


@pytest.mark.asyncio
async def test_4xx_and_5xx_fall_back_once():
    """Errors 400, 401, 500, 502 fall back to the existing sender once."""
    for error_code in (400, 401, 500, 503):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=MagicMock(status_code=error_code)), \
             patch("notifyhub_client.send_analysis_complete_email", new_callable=AsyncMock) as mock_fallback:

            await send_report_email("u@test.com", "Co", "c", "s")
            mock_fallback.assert_awaited_once()


@pytest.mark.asyncio
async def test_read_timeout_and_429_do_not_fall_back():
    """Read timeouts and 429 rate limit responses do NOT fall back to prevent duplicate sends."""
    # 1. Read timeout
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.ReadTimeout("Timeout")), \
         patch("notifyhub_client.send_analysis_complete_email", new_callable=AsyncMock) as mock_fallback:

        result = await send_report_email("u@test.com", "Co", "c", "s")
        assert result is False
        mock_fallback.assert_not_called()

    # 2. Rate limit 429
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=MagicMock(status_code=429)), \
         patch("notifyhub_client.send_analysis_complete_email", new_callable=AsyncMock) as mock_fallback:

        result = await send_report_email("u@test.com", "Co", "c", "s")
        assert result is False
        mock_fallback.assert_not_called()


@pytest.mark.asyncio
async def test_logs_never_contain_api_key_pdf_or_email(capsys):
    """Verify stdout/stderr logs never leak the API key, base64 PDF bytes, or raw email."""
    secret_key = "super-confidential-api-key-999"
    secret_email = "confidential-user-456@enterprise.org"
    os.environ["NOTIFYHUB_API_KEY"] = secret_key

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=MagicMock(status_code=202)):
        await send_report_email(
            to_email=secret_email,
            company_name="SecretCo",
            company_id="c-sec",
            session_id="s-sec",
        )

    captured = capsys.readouterr()
    log_output = captured.out + captured.err
    assert secret_key not in log_output
    assert secret_email not in log_output


@pytest.mark.asyncio
async def test_analysis_flow_never_crashes_on_email_failure():
    """Email failure must never raise into or crash the analysis flow."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=Exception("Critical system error")), \
         patch("notifyhub_client.send_analysis_complete_email", new_callable=AsyncMock, side_effect=Exception("SMTP down")):

        # Should handle internally and not raise
        result = await send_report_email("u@test.com", "Co", "c", "s")
        assert result is False
