from __future__ import annotations

import mimetypes
import smtplib
from email.message import EmailMessage
from pathlib import Path


def build_message(settings, job: dict, packet: dict) -> EmailMessage:
    recipient = job.get("contact_email")
    if not recipient:
        raise ValueError("No recipient email exists for this job.")

    msg = EmailMessage()
    msg["From"] = settings.email_user
    msg["To"] = recipient
    msg["Subject"] = f"Application for {job.get('title', 'Role')} — {settings.candidate_name}"
    msg.set_content(packet["cover_letter_text"])

    attachments = [
        Path(packet["resume_output_path"]),
        Path(packet["cover_letter_path"]),
    ]

    for path in attachments:
        content = path.read_bytes()
        mime_type, _ = mimetypes.guess_type(str(path))
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=path.name)

    return msg


def send_application(settings, job: dict, packet: dict) -> None:
    message = build_message(settings, job, packet)

    with smtplib.SMTP(settings.email_host, settings.email_port, timeout=30) as server:
        if settings.email_use_tls:
            server.starttls()
        server.login(settings.email_user, settings.email_password)
        server.send_message(message)