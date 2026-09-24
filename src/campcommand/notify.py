"""Sends a batch's error report to the camp's contact.

Uses SMTP when CAMPCOMMAND_SMTP_HOST is set; otherwise just logs what it
would have sent, which is what local runs and CI do.
"""

import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from campcommand.clients import Client

log = logging.getLogger(__name__)


def send_report(client: Client, feed: str, source_file: str, report_path: Path) -> bool:
    subject = f"{client.name}: some rows in {source_file} need attention"
    host = os.environ.get("CAMPCOMMAND_SMTP_HOST")
    if not host:
        log.info(
            "would email %s <%s>: %s (%s)", client.contact_name, client.contact_email, subject, report_path
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("CAMPCOMMAND_SMTP_FROM", "data@campcommand.app")
    msg["To"] = f"{client.contact_name} <{client.contact_email}>"
    msg.set_content(
        f"Your {feed.replace('_', ' ')} upload was processed. Details are in the attached report."
    )
    msg.add_alternative(report_path.read_text(encoding="utf-8"), subtype="html")
    for attachment in report_path.parent.glob(f"{report_path.stem}_rows_to_fix.csv"):
        msg.add_attachment(attachment.read_bytes(), maintype="text", subtype="csv", filename=attachment.name)

    with smtplib.SMTP(host, int(os.environ.get("CAMPCOMMAND_SMTP_PORT", "587"))) as smtp:
        smtp.starttls()
        if user := os.environ.get("CAMPCOMMAND_SMTP_USER"):
            smtp.login(user, os.environ["CAMPCOMMAND_SMTP_PASSWORD"])
        smtp.send_message(msg)
    return True
