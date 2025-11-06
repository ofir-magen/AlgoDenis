import os
import asyncio
import time
import json
import re
from typing import List, Optional, Dict, Any, Tuple

from dotenv import load_dotenv

from ai import ask_with_sources
from telegram_listener import TelegramListener, TelegramMessenger
from log_utils import build_logger

# ========= ENV / Logger =========
load_dotenv()
logger = build_logger("main")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
SOURCE_CHANNEL_ID = int(os.getenv("SOURCE_CHANNEL_ID", "0"))
TARGET_GROUP_ID = int(os.getenv("TARGET_GROUP_ID", "0"))
USERS_GROUP_CHAT = int(os.getenv("UsersGroupChat", "0"))
RETRY_DELAY_SECONDS = float(os.getenv("TG_RETRY_DELAY", "15"))

if not BOT_TOKEN or not SOURCE_CHANNEL_ID or not TARGET_GROUP_ID:
    logger.error("Missing BOT_TOKEN / SOURCE_CHANNEL_ID / TARGET_GROUP_ID in .env")

# Global messenger to Telegram (target group)
messenger: Optional[TelegramMessenger] = None

# ========= Helpers: extract JSON from GPT answer =========

_CODE_FENCE_RE = re.compile(r"```(\s*json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _find_balanced_braces_block(s: str) -> Tuple[int, int]:
    start = s.find("{")
    if start == -1:
        return -1, -1
    depth = 0
    for i in range(start, len(s)):
        c = s[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    return -1, -1


def _normalize_maybe_python_dict_to_json(raw: str) -> str:
    tmp_guard = "\uFFFF"
    raw = raw.replace("\\'", tmp_guard)
    norm = (
        raw.replace("'", '"')
           .replace(" None", " null").replace(": None", ": null")
           .replace(" True", " true").replace(": True", ": true")
           .replace(" False", " false").replace(": False", ": false")
    )
    norm = norm.replace(tmp_guard, "\\'")
    return norm


def extract_json_from_text(full_text: str, remove_from_text: bool = True):
    """
    מחלץ JSON מתוך טקסט (תשובת GPT).
    מנסה קודם ```json ...``` או ``` ...``` ואז בלוק { ... } מאוזן.
    מחזיר: (text_without_json, obj_or_none, raw_block_or_none)
    """
    if not full_text:
        return full_text, None, None

    text = full_text

    # 1) fenced code block
    m = _CODE_FENCE_RE.search(text)
    if m:
        raw_block = (m.group(2) or "").strip()
        if raw_block:
            obj = None
            try:
                obj = json.loads(raw_block)
            except Exception:
                try:
                    obj = json.loads(_normalize_maybe_python_dict_to_json(raw_block))
                except Exception:
                    obj = None

            if remove_from_text:
                text = (text[:m.start()] + text[m.end():]).strip()
            return text, obj, raw_block

    # 2) balanced { ... }
    s, e = _find_balanced_braces_block(text)
    if s != -1 and e != -1:
        raw_block = text[s:e].strip()
        obj = None
        try:
            obj = json.loads(raw_block)
        except Exception:
            try:
                obj = json.loads(_normalize_maybe_python_dict_to_json(raw_block))
            except Exception:
                obj = None

        if remove_from_text:
            text = (text[:s] + text[e:]).strip()
        return text, obj, raw_block

    return text, None, None

# ========= Trading helpers =========

def _to_float_or_none(x):
    if x is None:
        return None
    try:
        return float(str(x).strip())
    except Exception:
        return None


def orderList(last_rate_raw):
    """
    בונה פקודת מסחר בסיסית מתוך Last Rate מה-inline_json.
    """
    last_rate = _to_float_or_none(last_rate_raw)
    if last_rate is None:
        return None
    r = lambda v: float(f"{v:.4f}")
    return {
        "ENTRY_PRICE": r(last_rate),
        "STOP_LOSS": r(last_rate * 0.9),
        "TAKE_PROFIT": r(last_rate * 2),
    }


def calcPresentGoodRate(ai_json: Dict[str, Any]) -> bool:
    print("=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=")
    """
    בודק אם האות טוב בהתאם לפרמטרים ב-data.json.
    מניח של-ai_json יש מפתחות prob_up, prob_down, prob_stable (0-100).
    התאם לפי מה שאתה מחזיר מה-GPT.
    """
    if not ai_json:
        print("ai_json is None")
        return False

    try:
        with open("../db/settings.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to load data.json: {e}")

        logger.exception(f"Failed to load data.json: {e}")
        return False

    min1 = data.get("min1")
    max1 = data.get("max1")
    min2 = data.get("min2")
    max2 = data.get("max2")

    prob_up = ai_json.get("prob_up")
    prob_down = ai_json.get("prob_down")
    prob_stable = ai_json.get("prob_stable")

    try:
        print(f"prob_up: {prob_up}, prob_down: {prob_down}, confiprob_stabledence: {prob_stable}")
        prob_up = float(prob_up)
        prob_down = float(prob_down)
        prob_stable = float(prob_stable)
        print(f"Converted to float: prob_up: {prob_up}, prob_down: {prob_down}, prob_stable: {prob_stable}")
    except (TypeError, ValueError):
        print("Invalid prob_up/prob_down/prob_stable values")
        return False

    if None in (min1, max1, min2, max2):
        return False

    cond1 = min1 <= (prob_up - prob_down) <= max1
    cond2 = min2 <= (prob_up - prob_stable) <= max2
    print("cond1:", cond1, "cond2:", cond2)

    return cond1 and cond2

# ========= Processing Logic =========

async def process_urls(
    urls: List[str],
    question_text: str = "",
    link_text: str = "",
    matrix_text: str = "",
    inline_json: Optional[Dict[str, Any]] = None,
):
    """
    נקרא מ-TelegramListener כשהתקבלה הודעה עם לינקים.
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"process_urls invoked at {ts} with {len(urls)} URLs; link_text='{link_text}'")

    if not urls:
        err = "No URLs provided from Telegram message."
        logger.error(err)
        if messenger:
            parts = ["שגיאה בעיבוד הודעה מהטלגרם:", err]
            if matrix_text:
                parts += ["", "מטריצה:", matrix_text]
            if inline_json:
                parts += [
                    "",
                    "JSON:",
                    "```json",
                    json.dumps(inline_json, ensure_ascii=False, indent=2),
                    "```",
                ]
            await messenger.send_text_with_button("\n".join(parts))
        return

    # --- קריאה ל-GPT ---
    try:
        logger.info(f"Sending {len(urls)} URLs to GPT…")
        answer = await asyncio.to_thread(ask_with_sources, None, None, urls)
        logger.info("Received answer from GPT.")
    except Exception as e:
        answer = f"AI processing failed: {e}"
        logger.exception(f"ask_with_sources failed: {e}")

    answer_text = str(answer)

    # --- חילוץ JSON מתוך תשובת GPT ---
    answer_text_wo_json, ai_json, ai_json_raw = extract_json_from_text(
        answer_text,
        remove_from_text=True,
    )

    if ai_json is not None:
        logger.info("AI JSON extracted: %s", json.dumps(ai_json, ensure_ascii=False))
    else:
        logger.info("No AI JSON found in GPT answer")

    # --- חישוב flag לפי ai_json ---
    flag = None
    if ai_json is not None:
        try:
            flag = calcPresentGoodRate(ai_json)
            logger.info(f"calcPresentGoodRate -> {flag}")
        except Exception as e:
            logger.exception(f"calcPresentGoodRate failed: {e}")

    # --- חישוב orderRate מה-inline_json ---
    orderRate = None
    if inline_json:
        try:
            orderRate = orderList(inline_json.get("Last Rate"))
            logger.info("Order rate computed: %s", json.dumps(orderRate, ensure_ascii=False))
        except Exception as e:
            logger.exception(f"orderList failed: {e}")

    # --- בניית טקסט הסיכום שנשלח ל-TARGET_GROUP_ID ---
    msg_parts = [
        "כותרת ההודעה:",
        (question_text or "(ללא כותרת)").strip(),
        "",
        "קישור שצורף:",
        (link_text or "(אין קישור)").strip(),
        "",
        "תשובה מ-AI:",
        answer_text_wo_json.strip(),
    ]

    if matrix_text:
        msg_parts += ["", "מטריצה:", "```", matrix_text.strip(), "```"]

    if inline_json:
        msg_parts += [
            "",
            "JSON (מקור מהטלגרם):",
            "```json",
            json.dumps(inline_json, ensure_ascii=False, indent=2),
            "```",
        ]

    if ai_json:
        msg_parts += [
            "",
            "AI JSON (מתוך תשובת GPT):",
            "```json",
            json.dumps(ai_json, ensure_ascii=False, indent=2),
            "```",
        ]

    if orderRate:
        msg_parts += [
            "",
            "פקודת מסחר (מה-Rate המקורי):",
            "```json",
            json.dumps(orderRate, ensure_ascii=False, indent=2),
            "```",
        ]

    full_text = "\n".join(msg_parts)

    # --- שליחה: כל הפרמטרים עוברים לפונקציה, היא רק מדפיסה לעת עתה ---
    if messenger:
        try:
            await messenger.send_text_with_button(
                full_text,
                orderRate=orderRate,
                flag=flag,
                inline_json=inline_json,
                ai_json=ai_json,
            )
        except Exception as e:
            logger.exception(f"Error sending message to Telegram: {e}")

# ========= Init and run =========

async def amain():
    global messenger

    loop = asyncio.get_running_loop()
    logger.info("Starting amain()")

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set in .env — exiting.")
        return
    if not SOURCE_CHANNEL_ID:
        logger.error("SOURCE_CHANNEL_ID not set in .env — exiting.")
        return
    if not TARGET_GROUP_ID:
        logger.error("TARGET_GROUP_ID not set in .env — exiting.")
        return

    messenger = TelegramMessenger(BOT_TOKEN, TARGET_GROUP_ID)
    logger.info(f"TelegramMessenger ready for group {TARGET_GROUP_ID}")

    try:
        listener = TelegramListener(
            BOT_TOKEN,
            SOURCE_CHANNEL_ID,
            on_urls=process_urls,
        )
        listener.start(loop)
        logger.info("TelegramListener started.")
    except Exception as e:
        logger.exception(f"Failed to start TelegramListener: {e}")
        return

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
            logger.exception(
                f"Top-level run() error: {e}; will retry in {RETRY_DELAY_SECONDS}s"
            )
            time.sleep(RETRY_DELAY_SECONDS)

if __name__ == "__main__":
    run()
