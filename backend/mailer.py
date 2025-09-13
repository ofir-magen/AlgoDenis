# backend/mailer.py
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Dict, Any

def _smtp_settings():
    return {
        "host": os.getenv("SMTP_HOST", ""),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASS", ""),
        "sender": os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "") or "no-reply@example.com"),
        "starttls": os.getenv("SMTP_STARTTLS", "1") == "1",
        "ssl": os.getenv("SMTP_SSL", "0") == "1",
        "admin": os.getenv("ADMIN_NOTIFY_EMAIL", ""),
        "send_user": os.getenv("EMAIL_SEND_TO_USER", "1") == "1",
        "send_admin": os.getenv("EMAIL_SEND_TO_ADMIN", "1") == "1",
        "skip_verify": os.getenv("SMTP_SKIP_VERIFY", "0") == "1",  # אופציונלי: לעקוף אימות (לא מומלץ)
    }

def _tls_context(skip_verify: bool = False) -> ssl.SSLContext:
    if skip_verify:
        # לא מומלץ לפרודקשן — רק דיאגנוסטיקה זמנית
        return ssl._create_unverified_context()
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
    return ctx

def _send_email(to_email: str, subject: str, text_body: str):
    cfg = _smtp_settings()
    if not (cfg["host"] and (cfg["user"] or cfg["sender"])):
        print("[mailer] SMTP not configured, skipping send.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = to_email
    msg.set_content(text_body)

    try:
        if cfg["ssl"]:
            # SMTPS (465)
            context = _tls_context(cfg["skip_verify"])
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context) as server:
                if cfg["user"]:
                    server.login(cfg["user"], cfg["password"])
                server.send_message(msg)
        else:
            # STARTTLS (587)
            with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
                server.ehlo()
                if cfg["starttls"]:
                    context = _tls_context(cfg["skip_verify"])
                    server.starttls(context=context)
                    server.ehlo()
                if cfg["user"]:
                    server.login(cfg["user"], cfg["password"])
                server.send_message(msg)
        print(f"[mailer] sent to {to_email}")
    except Exception as e:
        print(f"[mailer] send failed to {to_email}: {type(e).__name__}: {e}")

def _fmt(v: Any) -> str:
    return "" if v is None else str(v)

def send_on_registration(user: Dict[str, Any], extra_message: str = ""):
    first_name = _fmt(user.get("first_name"))
    last_name  = _fmt(user.get("last_name"))
    email      = _fmt(user.get("email"))
    phone      = _fmt(user.get("phone"))
    telegram   = _fmt(user.get("telegram_username") or user.get("telegram"))
    username   = _fmt(user.get("username"))
    active_until = _fmt(user.get("active_until"))
    approved   = _fmt(user.get("approved"))

    user_subject = "ברוך הבא | Algo Trade"
    user_body = f"""שלום {first_name or 'יקר/ה'},

נרשמת בהצלחה לשירות.
להלן פרטי הרישום שהזנת:
• שם: {first_name} {last_name}
• מייל: {email}
• טלפון: {phone}
• טלגרם: {telegram}
• תוקף: {active_until}

{extra_message.strip() if extra_message else ''}
לכל בעיה,יש לפנות למייל זה.
תודה ובהצלחה,
Algo Trade
"""

    admin_subject = "רישום חדש – Algo Trade"
    admin_body = f"""נרשם/ה משתמש/ת חדש/ה:

ID: {user.get('id', '')}
שם: {first_name} {last_name}
מייל: {email}
טלפון: {phone}
טלגרם: {telegram}
שם משתמש: {username}
תוקף: {active_until}
מאושר: {approved}

הודעת תוספת:
{extra_message.strip() if extra_message else '(ללא)'}
"""

    cfg = _smtp_settings()
    if cfg["send_user"] and email:
        _send_email(email, user_subject, user_body)
    if cfg["send_admin"] and cfg["admin"]:
        _send_email(cfg["admin"], admin_subject, admin_body)
