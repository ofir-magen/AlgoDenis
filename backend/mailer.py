# backend/mailer.py
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Dict, Any

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))        # 587 = STARTTLS
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "no-reply@example.com")

SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "1") == "1"   # ברירת מחדל: STARTTLS
SMTP_SSL      = os.getenv("SMTP_SSL", "0") == "1"        # לחלופין: SSL מלא (465)

# למי להודיע על רישום חדש (אופציונלי)
ADMIN_NOTIFY_EMAIL = os.getenv("ADMIN_NOTIFY_EMAIL", "")
EMAIL_SEND_TO_USER = os.getenv("EMAIL_SEND_TO_USER", "1") == "1"
EMAIL_SEND_TO_ADMIN = os.getenv("EMAIL_SEND_TO_ADMIN", "1") == "1"

def _send_email(to_email: str, subject: str, text_body: str):
    if not (SMTP_HOST and (SMTP_USER or SMTP_FROM)):
        print("[mailer] SMTP not configured, skipping send.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.set_content(text_body)

    try:
        if SMTP_SSL:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                if SMTP_STARTTLS:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
        print(f"[mailer] sent to {to_email}")
    except Exception as e:
        print(f"[mailer] send failed to {to_email}: {type(e).__name__}: {e}")

def _fmt(v: Any) -> str:
    return "" if v is None else str(v)

def send_on_registration(user: Dict[str, Any], extra_message: str = ""):
    """
    שולח מייל ברישום:
      - למשתמש (אם EMAIL_SEND_TO_USER=1)
      - לאדמין (אם ADMIN_NOTIFY_EMAIL ולפי EMAIL_SEND_TO_ADMIN)
    """
    # נחלץ שדות אם קיימים (לא קריטי אם חסר)
    first_name = _fmt(user.get("first_name"))
    last_name  = _fmt(user.get("last_name"))
    email      = _fmt(user.get("email"))
    phone      = _fmt(user.get("phone"))
    telegram   = _fmt(user.get("telegram_username") or user.get("telegram"))
    username   = _fmt(user.get("username"))
    active_until = _fmt(user.get("active_until"))
    approved   = _fmt(user.get("approved"))

    # הודעה למשתמש
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
לאחר בדיקת התשלום, נכניס אותך לקבוצת הטלגרם
לכל בעיה,יש לפנות למייל זה.
תודה ובהצלחה,
Algo Trade
"""

    # הודעה לאדמין
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

    if EMAIL_SEND_TO_USER and email:
        _send_email(email, user_subject, user_body)

    if EMAIL_SEND_TO_ADMIN and ADMIN_NOTIFY_EMAIL:
        _send_email(ADMIN_NOTIFY_EMAIL, admin_subject, admin_body)
