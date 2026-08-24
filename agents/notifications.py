import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

logger = logging.getLogger("labmind.notifications")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")
SMS_API_URL = os.getenv("SMS_API_URL", "")
SMS_API_KEY = os.getenv("SMS_API_KEY", "")


def send_email(to: str, subject: str, body: str) -> bool:
    if not SMTP_HOST or not SMTP_FROM:
        logger.warning("Email notification skipped: SMTP not configured")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_FROM
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, to, msg.as_string())

        logger.info("Email notification sent to %s: %s", to, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
        return False


def send_sms(to: str, message: str) -> bool:
    if not SMS_API_URL or not SMS_API_KEY:
        logger.warning("SMS notification skipped: SMS API not configured")
        return False

    try:
        import requests
        response = requests.post(
            SMS_API_URL,
            json={"to": to, "message": message},
            headers={"Authorization": f"Bearer {SMS_API_KEY}"},
            timeout=10,
        )
        response.raise_for_status()
        logger.info("SMS notification sent to %s", to)
        return True
    except Exception as e:
        logger.error("Failed to send SMS to %s: %s", to, e)
        return False


def notify_critical_value(
    clinician_email: Optional[str],
    clinician_phone: Optional[str],
    specimen_token: str,
    value_summary: str,
    routed_at: str,
):
    subject = f"CRITICAL VALUE ALERT - Specimen {specimen_token[:12]}..."
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #dc2626;">CRITICAL VALUE ALERT</h2>
        <p><strong>Specimen:</strong> {specimen_token}</p>
        <p><strong>Value:</strong> {value_summary}</p>
        <p><strong>Time:</strong> {routed_at}</p>
        <hr>
        <p style="color: #6b7280; font-size: 12px;">
            This is an automated alert from LabMind ATLAS. 
            Please acknowledge this alert in the dashboard.
        </p>
    </body>
    </html>
    """
    sms_message = f"CRITICAL VALUE: {value_summary} (Specimen: {specimen_token[:12]}...). Acknowledge in LabMind."

    if clinician_email:
        send_email(clinician_email, subject, html_body)
    if clinician_phone:
        send_sms(clinician_phone, sms_message)
