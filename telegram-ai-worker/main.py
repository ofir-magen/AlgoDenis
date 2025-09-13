# main.py
import os
import sys
import asyncio
import time
from typing import List, Optional

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ai import ask_with_sources
from telegram_listener import TelegramListener, TelegramMessenger

# ========= ENV =========
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
SOURCE_CHANNEL_ID = int(os.getenv("SOURCE_CHANNEL_ID", "0"))
TARGET_GROUP_ID = int(os.getenv("TARGET_GROUP_ID", "0"))
USERS_GROUP_CHAT = int(os.getenv("UsersGroupChat", "0"))  # לערוץ/קבוצה שמקבלת סיכום בלחיצה
RETRY_DELAY_SECONDS = float(os.getenv("TG_RETRY_DELAY", "15"))

if not BOT_TOKEN or not SOURCE_CHANNEL_ID or not TARGET_GROUP_ID:
    print("[BOOT] חסרים BOT_TOKEN / SOURCE_CHANNEL_ID / TARGET_GROUP_ID ב-.env", file=sys.stderr)

# שליח לטלגרם (קבוצה יעד)
messenger: Optional[TelegramMessenger] = None

# ========= לוגיקת עיבוד =========
async def process_urls(urls: List[str], question_text: str = "", link_text: str = "", matrix_text: str = ""):
    """
    נקראת ע״י TelegramListener כשהיא מזהה פוסט עם קישורים.
    urls        - כל הקישורים חוץ מהראשון (כמו בקוד שלך)
    question_text - הטקסט לאחר ניקוי קישורים/תוויות
    link_text   - הקישור הראשון (להצגה)
    matrix_text - מטריצה שזוהתה (לא נשלחת ל-GPT)
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    if not urls:
        err = "No URLs provided from Telegram message."
        print(f"[worker] {ts} - {err}", file=sys.stderr)
        # שליחת הודעת שגיאה עם כפתורים (אופציונלי)
        if messenger:
            parts = ["שגיאה בעיבוד הודעה מהטלגרם:", err]
            if matrix_text:
                parts += ["", "מטריצה:", matrix_text]
            await messenger.send_text_with_button("\n".join(parts))
        return

    try:
        print(f"[worker] {ts} - שולח ל-GPT עם {len(urls)} קישורים…")
        # שים לב: ai.py המקורי טוען PROMPT/QUESTION מה-.env ומתעלם מארגומנטים
        answer = await asyncio.to_thread(ask_with_sources, None, None, urls)
        print(f"[worker] {ts} - קיבלתי תשובה מ-GPT")
    except Exception as e:
        answer = f"AI processing failed: {e}"
        print(f"[worker] {ts} - {answer}", file=sys.stderr)

    # בניית טקסט מלא לטלגרם
    msg_parts = [
        "כותרת ההודעה:",
        (question_text or "(ללא כותרת)").strip(),
        "",
        "קישור שצורף:",
        (link_text or "(אין קישור)").strip(),
        "",
        "תשובה מ-AI:",
        str(answer).strip(),
    ]
    if matrix_text:
        msg_parts += ["", "מטריצה:", matrix_text.strip()]
    full_text = "\n".join(msg_parts)

    # שליחה לקבוצת היעד עם כפתורים
    if messenger:
        try:
            await messenger.send_text_with_button(full_text)
            print("[worker] נשלח לטלגרם ✓")
        except Exception as e:
            print(f"[TG] שגיאה בשליחה לקבוצה: {e}", file=sys.stderr)


# ========= אתחול והפעלת המאזין =========
async def amain():
    global messenger

    loop = asyncio.get_running_loop()

    # הכנת שליח לקבוצת היעד
    if BOT_TOKEN and TARGET_GROUP_ID:
        messenger = TelegramMessenger(BOT_TOKEN, TARGET_GROUP_ID)
        print(f"[TG] TelegramMessenger מוכן לקבוצה {TARGET_GROUP_ID}")
    else:
        print("[TG] TelegramMessenger לא הופעל (BOT_TOKEN/TARGET_GROUP_ID חסרים)")

    if not BOT_TOKEN:
        print("[TG] לא הוגדר BOT_TOKEN ב-.env — המאזין לא יופעל.", file=sys.stderr)
        return
    if not SOURCE_CHANNEL_ID:
        print("[TG] לא הוגדר SOURCE_CHANNEL_ID ב-.env — המאזין לא יופעל.", file=sys.stderr)
        return

    # מאזין
    listener = TelegramListener(
        BOT_TOKEN,
        SOURCE_CHANNEL_ID,
        on_urls=process_urls
    )
    listener.start(loop)  # מריץ polling בת׳רד נפרד, ומשתמש בלולאה הזו להריץ את הקולבק

    # הישארות רצה
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass


def run():
    while True:
        try:
            asyncio.run(amain())
            break
        except Exception as e:
            print(f"[BOOT] שגיאת ריצה: {type(e).__name__}: {e} — ניסיון חוזר בעוד {RETRY_DELAY_SECONDS}s", file=sys.stderr)
            time.sleep(RETRY_DELAY_SECONDS)


if __name__ == "__main__":
    run()
