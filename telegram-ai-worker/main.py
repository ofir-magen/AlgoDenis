import os
import sys
import asyncio
import time
from typing import List, Optional

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ai import ask_with_sources
from telegram_listener import TelegramListener, TelegramMessenger
from log_utils import build_logger

# ========= ENV =========
load_dotenv()
logger = build_logger("main")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
SOURCE_CHANNEL_ID = int(os.getenv("SOURCE_CHANNEL_ID", "0"))
TARGET_GROUP_ID = int(os.getenv("TARGET_GROUP_ID", "0"))
USERS_GROUP_CHAT = int(os.getenv("UsersGroupChat", "0"))  # group/channel for user summary on click
RETRY_DELAY_SECONDS = float(os.getenv("TG_RETRY_DELAY", "15"))

if not BOT_TOKEN or not SOURCE_CHANNEL_ID or not TARGET_GROUP_ID:
    logger.error("Missing BOT_TOKEN / SOURCE_CHANNEL_ID / TARGET_GROUP_ID in .env")

# Global messenger to Telegram (target group)
messenger: Optional[TelegramMessenger] = None

# ========= Processing Logic =========
async def process_urls(urls: List[str], question_text: str = "", link_text: str = "", matrix_text: str = ""):
    """
    Called by TelegramListener when a post with links is detected.
    urls         - all links except the first one (as in your code)
    question_text - text after removing links/labels
    link_text    - the first link (for display)
    matrix_text  - detected matrix (not sent to GPT)
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"process_urls invoked with {len(urls)} URLs; link_text='{link_text}'")

    if not urls:
        err = "No URLs provided from Telegram message."
        logger.error(err)
        if messenger:
            parts = ["שגיאה בעיבוד הודעה מהטלגרם:", err]
            if matrix_text:
                parts += ["", "מטריצה:", matrix_text]
            try:
                await messenger.send_text_with_button("\n".join(parts))
            except Exception as e:
                logger.exception(f"Failed sending error message to Telegram: {e}")
        return

    # Call GPT worker
    try:
        logger.info(f"Sending {len(urls)} URLs to GPT…")
        answer = await asyncio.to_thread(ask_with_sources, None, None, urls)
        logger.info("Received answer from GPT.")
    except Exception as e:
        answer = f"AI processing failed: {e}"
        logger.exception(f"ask_with_sources failed: {e}")

    # Build final text for Telegram
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

    # Send to target group with buttons
    if messenger:
        try:
            await messenger.send_text_with_button(full_text)
            logger.info("Message sent to Telegram target group successfully.")
        except Exception as e:
            logger.exception(f"Error sending message to Telegram group: {e}")

# ========= Init and run the listener =========
async def amain():
    global messenger

    loop = asyncio.get_running_loop()
    logger.info("Starting amain()")

    if BOT_TOKEN and TARGET_GROUP_ID:
        messenger = TelegramMessenger(BOT_TOKEN, TARGET_GROUP_ID)
        logger.info(f"TelegramMessenger ready for group {TARGET_GROUP_ID}")
    else:
        logger.warning("TelegramMessenger not started (missing BOT_TOKEN/TARGET_GROUP_ID)")

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set in .env — listener will not start.")
        return
    if not SOURCE_CHANNEL_ID:
        logger.error("SOURCE_CHANNEL_ID not set in .env — listener will not start.")
        return

    # Listener
    try:
        listener = TelegramListener(
            BOT_TOKEN,
            SOURCE_CHANNEL_ID,
            on_urls=process_urls
        )
        listener.start(loop)  # runs polling in a separate thread, uses this loop for the callback
        logger.info("TelegramListener started.")
    except Exception as e:
        logger.exception(f"Failed to start TelegramListener: {e}")
        return

    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("amain() cancelled; shutting down.")

def run():
    logger.info("Entering run() loop")
    while True:
        try:
            asyncio.run(amain())
            logger.info("amain() returned; breaking run() loop")
            break
        except Exception as e:
            logger.exception(f"Top-level run() error: {e}; will retry in {RETRY_DELAY_SECONDS}s")
            time.sleep(RETRY_DELAY_SECONDS)

if __name__ == "__main__":
    run()
