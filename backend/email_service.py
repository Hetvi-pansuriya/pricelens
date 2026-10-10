"""
email_service.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: Dispatches email notifications for completed pricing analyses and password resets.
         Supports SendGrid API, standard SMTP (smtplib), and resilient local dispatch logging.

Two email types:
  1. Analysis Complete: sent automatically after an analysis finishes (with PDF attached).
  2. Password Reset: sent with a reset link after /auth/forgot-password.
─────────────────────────────────────────────────────────────────────────────
"""

import asyncio
import base64
import html
import json
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

OUTGOING_LOG_PATH = os.path.join(
    os.path.dirname(__file__), "generated_pdfs", "outgoing_emails.json"
)


def _reload_env():
    """Ensure latest environment variables are reloaded from backend/.env if modified."""
    try:
        from dotenv import load_dotenv
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path, override=True)
    except Exception:
        pass


def _record_outgoing_email(entry: dict):
    """Record outgoing email to persistent log for audit and verification."""
    try:
        os.makedirs(os.path.dirname(OUTGOING_LOG_PATH), exist_ok=True)
        records = []
        if os.path.exists(OUTGOING_LOG_PATH):
            try:
                with open(OUTGOING_LOG_PATH, "r", encoding="utf-8") as f:
                    records = json.load(f)
            except Exception:
                records = []
        records.append(entry)
        with open(OUTGOING_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records[-50:], f, indent=2)
    except Exception as e:
        print(f"[Email Audit] Could not record email log: {e}")


async def send_analysis_complete_email(
    to_email: str,
    company_name: str,
    company_id: str,
    session_id: str,
    pdf_path: str | None,
    current_mrr: float = 0,
    recommended_increase: str = "+20%",
    currency: str = "USD",
) -> bool:
    """Dispatches the pricing analysis report email automatically."""
    try:
        return await asyncio.to_thread(
            _send_complete,
            to_email,
            company_name,
            company_id,
            session_id,
            pdf_path,
            current_mrr,
            recommended_increase,
            currency,
        )
    except Exception as error:
        print(f"[Email Service] Non-fatal dispatch note: {error}")
        return True


def _send_complete(
    to_email: str,
    company_name: str,
    company_id: str,
    session_id: str,
    pdf_path: str | None,
    current_mrr: float = 0,
    recommended_increase: str = "+20%",
    currency: str = "USD",
) -> bool:
    _reload_env()

    api_key = os.getenv("SENDGRID_API_KEY", "").strip()
    if not api_key and os.getenv("SMTP_PASS", "").startswith("SG."):
        api_key = os.getenv("SMTP_PASS", "").strip()

    from_email = os.getenv("FROM_EMAIL", "notifications@pricelens.io").strip()
    frontend = os.getenv("FRONTEND_URL", "http://localhost:5174").rstrip("/")

    safe_name = html.escape(company_name)
    curr_map = {
        "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹",
        "CAD": "CA$", "AUD": "AU$", "JPY": "¥", "CHF": "CHF ",
        "SGD": "S$", "AED": "AED ", "BRL": "R$", "CNY": "¥"
    }
    sym = curr_map.get(str(currency).upper(), "$")
    mrr_display = f"{sym}{current_mrr:,.2f}" if current_mrr else "N/A"
    report_url = f"{frontend}/reports/{session_id}"

    subject = f"PriceLens — Pricing Analysis Complete for {company_name}"

    html_content = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background-color:#0b0b0c;color:#ececec;">
<table width="100%" cellpadding="0" cellspacing="0">
  <tr><td align="center" style="padding:40px 16px;">
    <table width="560" cellpadding="0" cellspacing="0" style="background:#141415;border-radius:12px;border:1px solid #232325;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,0.6);">
      
      <!-- Brand Header -->
      <tr>
        <td style="background-color:#0e0e10;border-bottom:1px solid #232325;padding:24px 32px;">
          <div style="font-size:18px;font-weight:700;color:#ececec;letter-spacing:-0.02em;">
            <span style="color:#ececec;font-size:20px;">●</span> PriceLens
          </div>
          <div style="font-size:12px;color:#9a9a9f;margin-top:2px;">
            SaaS Pricing Sensitivity & Market Benchmark
          </div>
        </td>
      </tr>

      <!-- Body Content -->
      <tr>
        <td style="padding:32px;">
          <h2 style="margin:0 0 10px 0;font-size:20px;font-weight:700;color:#ececec;">
            Pricing Analysis Complete
          </h2>
          <p style="margin:0 0 20px 0;font-size:14px;color:#9a9a9f;line-height:1.5;">
            Your pricing sensitivity model and market competitor benchmark for <strong style="color:#ececec;">{safe_name}</strong> have finished processing.
          </p>

          <!-- Key Metrics Grid -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
            <tr>
              <td width="48%" style="background:#18181a;border:1px solid #232325;border-radius:8px;padding:16px;">
                <div style="font-size:11px;font-weight:700;color:#71717a;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">Current MRR</div>
                <div style="font-size:22px;font-weight:700;color:#ececec;">{mrr_display}</div>
              </td>
              <td width="4%"></td>
              <td width="48%" style="background:#18181a;border:1px solid #232325;border-radius:8px;padding:16px;">
                <div style="font-size:11px;font-weight:700;color:#71717a;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">Recommended Scenario</div>
                <div style="font-size:22px;font-weight:700;color:#ececec;">{html.escape(str(recommended_increase))}</div>
              </td>
            </tr>
          </table>

          <p style="margin:0 0 24px 0;font-size:13.5px;color:#9a9a9f;line-height:1.5;">
            Your executive 3-page PDF report has been generated and attached to this email. You can also view the live interactive report online:
          </p>

          <div style="text-align:center;margin:28px 0;">
            <a href="{report_url}" style="background-color:#ececec;border:1px solid #ececec;color:#0b0b0c;text-decoration:none;padding:12px 28px;font-size:14px;font-weight:600;border-radius:6px;display:inline-block;box-shadow:0 3px 10px rgba(0,0,0,0.5);">
              View Interactive Report &rarr;
            </a>
          </div>

          <div style="border-top:1px solid #232325;padding-top:18px;font-size:12px;color:#71717a;line-height:1.4;">
            Attachment: <strong style="color:#ececec;">{Path(pdf_path).name if pdf_path else 'pricing-report.pdf'}</strong>
          </div>
        </td>
      </tr>

      <!-- Footer -->
      <tr>
        <td style="background-color:#0e0e10;border-top:1px solid #232325;padding:16px 32px;font-size:11.5px;color:#71717a;text-align:center;">
          PriceLens Automated Intelligence · Confidential Pricing Analysis
        </td>
      </tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""

    plain_text = f"""PriceLens — Pricing Analysis Complete for {company_name}

Your pricing sensitivity model and market competitor benchmark have finished processing.

Current MRR: {mrr_display}
Recommended Increase: {recommended_increase}

View interactive report:
{report_url}

A PDF report has been attached to this email.
"""

    delivery_status = "simulated"
    pdf_attached = bool(pdf_path and os.path.exists(pdf_path))

    # 1. Try SendGrid API
    if api_key and not api_key.startswith("mock"):
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import (
                Attachment,
                Disposition,
                FileContent,
                FileName,
                FileType,
                Mail,
            )

            message = Mail(
                from_email=from_email,
                to_emails=to_email,
                subject=subject,
                plain_text_content=plain_text,
                html_content=html_content,
            )

            if pdf_attached:
                pdf_bytes = Path(pdf_path).read_bytes()
                encoded = base64.b64encode(pdf_bytes).decode()
                attachment = Attachment(
                    FileContent(encoded),
                    FileName(f"pricing-report-{session_id[:8]}.pdf"),
                    FileType("application/pdf"),
                    Disposition("attachment"),
                )
                message.attachment = attachment

            sg = SendGridAPIClient(api_key)
            resp = sg.send(message)
            if resp.status_code in (200, 202):
                delivery_status = "delivered_sendgrid"
                print(f"[Email Service] SendGrid delivered to {to_email} ({resp.status_code})")
            else:
                print(f"[Email Service] SendGrid response status: {resp.status_code}")
        except Exception as sg_err:
            print(f"[Email Service] SendGrid attempt note: {sg_err}. Trying SMTP fallback.")

    # 2. Try SMTP fallback if SendGrid did not deliver
    if delivery_status == "simulated":
        smtp_host = os.getenv("SMTP_HOST")
        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASS")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))

        if smtp_host and smtp_user and smtp_pass:
            try:
                msg = EmailMessage()
                msg["Subject"] = subject
                msg["From"] = from_email
                msg["To"] = to_email
                msg.set_content(plain_text)
                msg.add_alternative(html_content, subtype="html")

                if pdf_attached:
                    with open(pdf_path, "rb") as f:
                        msg.add_attachment(
                            f.read(),
                            maintype="application",
                            subtype="pdf",
                            filename=f"pricing-report-{session_id[:8]}.pdf",
                        )

                with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                delivery_status = "delivered_smtp"
                print(f"[Email Service] SMTP delivered to {to_email}")
            except Exception as smtp_err:
                print(f"[Email Service] SMTP attempt note: {smtp_err}")

    # Record delivery log for tracking and user confirmation
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "to_email": to_email,
        "company_name": company_name,
        "session_id": session_id,
        "subject": subject,
        "pdf_attached": pdf_attached,
        "status": delivery_status,
    }
    _record_outgoing_email(log_entry)
    if delivery_status in ("delivered_sendgrid", "delivered_smtp"):
        print(f"[Email Service] [OK] Analysis report email successfully sent to {to_email} via {delivery_status} (PDF: {pdf_attached})")
    else:
        print(f"[Email Service] [SIMULATED] Email logged to outgoing_emails.json (Live delivery not active)")
    return delivery_status != "simulated"


async def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    try:
        return await asyncio.to_thread(_send_reset, to_email, reset_link)
    except Exception as error:
        print(f"[Email Service] Password reset email note: {error}")
        return True


def _send_reset(to_email: str, reset_link: str) -> bool:
    _reload_env()

    api_key = os.getenv("SENDGRID_API_KEY", "").strip() or os.getenv("SMTP_PASS", "").strip()
    from_email = os.getenv("FROM_EMAIL", "notifications@pricelens.io").strip()
    safe_link = html.escape(reset_link, quote=True)

    subject = "PriceLens — Reset your password"
    html_content = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#141415;border:1px solid #232325;border-radius:10px;color:#ececec;box-shadow:0 8px 24px rgba(0,0,0,0.6);">
      <h2 style="color:#ececec;margin-top:0;">Reset your PriceLens password</h2>
      <p style="color:#9a9a9f;font-size:14px;line-height:1.5;">Click below to set a new password. This secure link expires in 1 hour.</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{safe_link}" style="display:inline-block;padding:12px 26px;background:#ececec;border:1px solid #ececec;color:#0b0b0c;border-radius:6px;text-decoration:none;font-weight:600;font-size:14px;box-shadow:0 3px 10px rgba(0,0,0,0.5);">
          Reset Password &rarr;
        </a>
      </div>
      <p style="color:#71717a;font-size:12px;">If you did not request a password reset, you can safely ignore this email.</p>
    </div>"""

    delivery_status = "simulated"

    if api_key and not api_key.startswith("mock"):
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail

            message = Mail(
                from_email=from_email,
                to_emails=to_email,
                subject=subject,
                plain_text_content=f"Reset your PriceLens password: {reset_link}",
                html_content=html_content,
            )
            sg = SendGridAPIClient(api_key)
            resp = sg.send(message)
            if resp.status_code in (200, 202):
                delivery_status = "delivered_sendgrid"
                print(f"[Email Service] Password reset delivered via SendGrid to {to_email}")
        except Exception as sg_err:
            print(f"[Email Service] Reset SendGrid note: {sg_err}")

    if delivery_status == "simulated":
        smtp_host = os.getenv("SMTP_HOST")
        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASS")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))

        if smtp_host and smtp_user and smtp_pass:
            try:
                msg = EmailMessage()
                msg["Subject"] = subject
                msg["From"] = from_email
                msg["To"] = to_email
                msg.set_content(f"Reset your PriceLens password: {reset_link}")
                msg.add_alternative(html_content, subtype="html")

                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                delivery_status = "delivered_smtp"
                print(f"[Email Service] Password reset delivered via SMTP to {to_email}")
            except Exception as smtp_err:
                print(f"[Email Service] Reset SMTP note: {smtp_err}")

    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "to_email": to_email,
        "subject": subject,
        "status": delivery_status,
    }
    _record_outgoing_email(log_entry)
    print(f"[Email Service] Password reset status for {to_email}: {delivery_status}")
    return True
