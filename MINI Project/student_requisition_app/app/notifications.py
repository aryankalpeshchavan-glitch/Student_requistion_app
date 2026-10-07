"""Optional e-mail notifications (student gets their PDF and every status change).

Enabled only when SMTP settings exist (Streamlit secrets or environment):
SMTP_HOST, SMTP_PORT (587 STARTTLS / 465 SSL), SMTP_USER, SMTP_PASSWORD, SMTP_FROM.
All functions are best-effort: a mail failure never blocks a requisition.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

import config

log = logging.getLogger(__name__)


def enabled() -> bool:
    return bool(config.secret("SMTP_HOST") and config.secret("SMTP_FROM"))


def build_message(to: str, subject: str, body: str,
                  attachment: tuple[str, bytes] | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = config.secret("SMTP_FROM")
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if attachment:
        name, data = attachment
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=name)
    return msg


def send_email(to: str, subject: str, body: str,
               attachment: tuple[str, bytes] | None = None) -> bool:
    if not enabled() or not to:
        return False
    try:
        msg = build_message(to, subject, body, attachment)
        host, port = config.secret("SMTP_HOST"), int(config.secret("SMTP_PORT", "587"))
        user, pw = config.secret("SMTP_USER"), config.secret("SMTP_PASSWORD")
        if port == 465:
            smtp = smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(host, port, timeout=15)
        with smtp:
            if port != 465:
                smtp.starttls(context=ssl.create_default_context())
            if user:
                smtp.login(user, pw)
            smtp.send_message(msg)
        return True
    except Exception as exc:                       # noqa: BLE001 - must never break the app
        log.warning("E-mail to %s failed: %s", to, exc)
        return False


def notify_submission(rec: dict, pdf: bytes, filename: str) -> bool:
    body = (f"Dear {rec['student_name']},\n\n"
            f"Your {rec['app_type']} requisition has been submitted.\n\n"
            f"Requisition No.: {rec['req_no']}\n"
            f"Normal processing time: {config.SLA_WORKING_DAYS} working days.\n\n"
            "The completed form is attached. Print it, sign it, and submit it to your HoD "
            "with the supporting documents. You can track progress on the portal using "
            "your Requisition No. and Roll No.\n\n"
            f"{config.FORM_TITLE.title()} Portal")
    return send_email(rec["email"], f"Requisition {rec['req_no']} submitted", body,
                      (filename, pdf))


def notify_status(email: str, req_no: str, status: str, remarks: str) -> bool:
    body = (f"The status of your requisition {req_no} is now: {status}.\n"
            + (f"\nRemarks from the office: {remarks}\n" if remarks else "")
            + "\nYou can see the full history on the portal (Track Status).")
    return send_email(email, f"Requisition {req_no}: {status}", body)
