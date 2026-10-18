"""Stores every notification; optionally delivers by email/webhook. Never include configs or secrets."""
import json
import smtplib
import urllib.request
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Notification


def _deliver(n: Notification) -> str:
    results = []
    if settings.smtp_host and settings.notify_email_to:
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[AutoNetOps/{n.severity}] {n.title}"
            msg["From"], msg["To"] = settings.smtp_from, settings.notify_email_to
            msg.set_content(n.message)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
                s.starttls()
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
            results.append("email:ok")
        except Exception as e:
            results.append(f"email:failed({type(e).__name__})")
    if settings.webhook_url:
        try:
            body = json.dumps({"event": n.event, "severity": n.severity, "title": n.title, "message": n.message}).encode()
            req = urllib.request.Request(settings.webhook_url, data=body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).close()
            results.append("webhook:ok")
        except Exception as e:
            results.append(f"webhook:failed({type(e).__name__})")
    return ",".join(results)


def notify(db: Session, event: str, title: str, message: str = "", severity: str = "info",
           device_id: int | None = None) -> Notification:
    n = Notification(event=event, severity=severity, title=title[:200], message=message, device_id=device_id)
    db.add(n)
    db.commit()
    delivery = _deliver(n)
    if delivery:
        n.delivery = delivery[:200]
        db.commit()
    return n
