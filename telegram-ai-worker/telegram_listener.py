import asyncio
import os
import re
import threading
import time
from typing import Callable, List, Optional, Tuple, Dict, Any
import json

from telegram import Bot, Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest

from log_utils import build_logger

logger = build_logger("tg-listener")

RETRY_DELAY_SECONDS = float(os.getenv("TG_RETRY_DELAY", "15"))
UsersGroupChat = int(os.getenv("UsersGroupChat", "0"))


def _extract_urls(message_text: str, entities) -> List[str]:
    if not entities:
        return []
    urls: List[str] = []
    for ent in entities:
        t = getattr(ent, "type", None)
        if t == "url":
            try:
                raw = message_text[ent.offset: ent.offset + ent.length]
                cleaned = raw.strip().replace("\n", "")
                if cleaned.startswith("ttps://"):
                    cleaned = "h" + cleaned
                urls.append(cleaned)
            except Exception as e:
                logger.exception(f"_extract_urls url slice failed: {e}")
        elif t == "text_link" and getattr(ent, "url", None):
            try:
                cleaned = ent.url.strip().replace("\n", "")
                urls.append(cleaned)
            except Exception as e:
                logger.exception(f"_extract_urls text_link failed: {e}")

    seen = set()
    uniq: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    logger.info(f"_extract_urls found {len(uniq)} unique urls")
    return uniq


def _build_httpx_request_from_env() -> HTTPXRequest:
    proxy = os.getenv("TG_PROXY") or None
    http_version_env = os.getenv("TG_HTTP_VERSION", "").strip()
    kwargs = {
        "connect_timeout": 20.0,
        "read_timeout": 60.0,
        "write_timeout": 60.0,
        "pool_timeout": 20.0,
    }
    if proxy:
        kwargs["proxy"] = proxy
    if http_version_env in ("1.1", "2", "2.0"):
        kwargs["http_version"] = http_version_env
    logger.info(
        f"HTTPXRequest built (proxy={bool(proxy)}, http_version={http_version_env or 'default'})"
    )
    return HTTPXRequest(**kwargs)


# ===== Inline "JSON" extractor =====
_PYDICT_BLOCK_RE = re.compile(r"\{[\s\S]*?\}", re.MULTILINE)


def extract_inline_pyjson(full_text: str, remove_from_text: bool = False):
    """
    מאתר dict פייתון-סטייל מתוך ההודעה, מנרמל ל-JSON ומחזיר כ-dict.
    :return: (text_after, obj_or_none, raw_block_or_none)
    """
    if not full_text:
        return full_text, None, None

    m = _PYDICT_BLOCK_RE.search(full_text)
    if not m:
        return full_text, None, None

    raw = m.group(0).strip()

    normalized = (
        raw.replace("\\'", "\uFFFF")
        .replace("'", '"')
        .replace("\uFFFF", "\\'")
        .replace(": None", ": null")
        .replace(":  None", ": null")
        .replace(" None,", " null,")
        .replace(" True", " true")
        .replace(" False", " false")
    )

    obj = None
    try:
        obj = json.loads(normalized)
    except Exception:
        obj = None

    if remove_from_text:
        new_text = (full_text[:m.start()] + full_text[m.end():]).strip()
    else:
        new_text = full_text

    return new_text, obj, raw


# ===== Matrix parsing =====
_ARRAY_ROW_RE = re.compile(
    r"^\s*\[\s*-?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?\s*(?:,\s*-?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?\s*)+\]\s*$"
)


def _extract_trailing_bracket_matrix(lines: List[str]) -> Tuple[int, str]:
    i = len(lines) - 1
    collected: List[str] = []
    while i >= 0 and _ARRAY_ROW_RE.match(lines[i]):
        collected.append(lines[i])
        i -= 1
    collected.reverse()
    if len(collected) >= 2:
        return i + 1, "\n".join(collected).strip()
    return -1, ""


def _extract_trailing_fenced_block(text: str) -> Tuple[int, int, str]:
    fence = "```"
    last_fence = text.rfind(fence)
    if last_fence == -1:
        return -1, -1, ""
    closing = text.rfind(fence)
    if closing == -1 or closing == last_fence:
        return -1, -1, ""
    if text[closing + len(fence) :].strip():
        return -1, -1, ""
    opening = text.rfind(fence, 0, closing)
    if opening == -1:
        return -1, -1, ""
    header = text[opening : opening + 10].lower()
    if not header.startswith("```"):
        return -1, -1, ""
    code = text[opening + len(fence) : closing].strip()
    if not code:
        return -1, -1, ""
    return opening, closing + len(fence), code


def _split_text_and_trailing_matrix(text: str, max_chars: int = 12000) -> Tuple[str, str]:
    raw = text.rstrip()
    lines = raw.splitlines()
    start_idx, mat = _extract_trailing_bracket_matrix(lines)
    if start_idx != -1:
        body = "\n".join(lines[:start_idx]).rstrip()
        m = mat if len(mat) <= max_chars else (mat[:max_chars] + "\n...[truncated]...")
        return body, m

    s, e, code = _extract_trailing_fenced_block(raw)
    if s != -1:
        body = raw[:s].rstrip()
        m = code if len(code) <= max_chars else (code[:max_chars] + "\n...[truncated]...")
        return body, m

    tag = re.search(r"\[MATRIX\]([\s\S]+)\[/MATRIX\]\s*$", raw, re.IGNORECASE)
    if tag:
        body = raw[:tag.start()].rstrip()
        code = tag.group(1).strip()
        m = code if len(code) <= max_chars else (code[:max_chars] + "\n...[truncated]...")
        return body, m

    return raw, ""


# ===== Helper: extract AI fields (company/symbols) from GPT answer text =====
def _extract_ai_fields_from_text(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    מחלץ:
    - שם החברה: ...
    - סימבול ת״א: ...
    - סימבול ארה״ב: ... / סימבול ארהב:
    מתוך קטע 'תשובה מ-AI:' שנמצא בתוך text.
    """
    if not text:
        return None, None, None

    anchor = "תשובה מ-AI:"
    idx = text.find(anchor)
    if idx == -1:
        return None, None, None

    after = text[idx + len(anchor):].strip()
    company = None
    tase = None
    us = None

    for line in after.splitlines():
        s = line.strip()
        if not s:
            continue

        if s.startswith("שם החברה:"):
            company = s.split(":", 1)[1].strip() or None
        elif (
            s.startswith("סימבול ת״א:")
            or s.startswith("סימבול תא:")
            or s.startswith("סימבול ת\"א:")
        ):
            tase = s.split(":", 1)[1].strip() or None
        elif (
            s.startswith("סימבול ארה״ב:")
            or s.startswith("סימבול ארהב:")
            or s.startswith("סימבול ארה\"ב:")
        ):
            us = s.split(":", 1)[1].strip() or None

        if company and tase and us:
            break

    return company, tase, us


# ===== Telegram Listener =====
class TelegramListener:
    def __init__(
        self,
        bot_token: str,
        channel_id: int,
        # callback: (urls, question_text, link_text, matrix_text, inline_json)
        on_urls: Callable[
            [List[str], str, str, str, Optional[Dict[str, Any]]], asyncio.Future
        ],
    ):
        self._bot_token = bot_token
        self._channel_id = channel_id
        self._on_urls = on_urls
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._request = _build_httpx_request_from_env()
        self._app = None

    def _build_app(self):
        logger.info("Building telegram Application instance")
        app = (
            ApplicationBuilder()
            .token(self._bot_token)
            .request(self._request)
            .build()
        )

        async def on_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                post = update.channel_post
                if not post or post.chat_id != self._channel_id:
                    return

                text = post.text or post.caption or ""
                entities = post.entities if post.text else post.caption_entities
                ts = post.date.strftime("%Y-%m-%d %H:%M:%S")
                urls = _extract_urls(text, entities)

                logger.info(
                    f"Channel post at {ts} | text_len={len(text)} | urls={len(urls)}"
                )

                question_text = text
                link_text = ""
                rest_urls: List[str] = []

                if urls:
                    link_text = urls[0]
                    rest_urls = urls[1:]

                    # הסרת ה-URLs מהטקסט
                    for u in [link_text] + rest_urls:
                        question_text = question_text.replace(u, "")

                    # הסרת טקסט מוצג של text_link
                    text_link_texts = []
                    for ent in entities or []:
                        if getattr(ent, "type", None) == "text_link":
                            try:
                                shown = text[ent.offset : ent.offset + ent.length]
                                text_link_texts.append(shown.strip())
                            except Exception as e:
                                logger.exception(
                                    f"extract shown text_link failed: {e}"
                                )
                    for shown in text_link_texts:
                        question_text = question_text.replace(shown, "")

                # חילוץ inline JSON
                question_text, inline_json, inline_json_raw = extract_inline_pyjson(
                    question_text,
                    remove_from_text=True,
                )
                if inline_json is not None:
                    logger.info(f"Inline JSON extracted: {inline_json}")

                # חילוץ מטריצה מהסוף
                question_text, matrix_text = _split_text_and_trailing_matrix(
                    question_text.strip()
                )

                logger.info(
                    "Post parsed: question_text_len=%d, link_text='%s', rest_urls=%d, matrix=%s",
                    len(question_text),
                    link_text,
                    len(rest_urls),
                    "yes" if matrix_text else "no",
                )

                # קריאה ל-callback רק אם יש URLs (כמו במקור)
                if urls:
                    if self._loop and not self._loop.is_closed():
                        asyncio.run_coroutine_threadsafe(
                            self._on_urls(
                                rest_urls,
                                question_text,
                                link_text,
                                matrix_text,
                                inline_json,
                            ),
                            self._loop,
                        )
                else:
                    # רק לוג אם אין לינקים
                    _, matrix_only = _split_text_and_trailing_matrix(
                        question_text.strip()
                    )
                    logger.info(
                        "No URLs found in post. matrix=%s",
                        "yes" if matrix_only else "no",
                    )

            except Exception as e:
                logger.exception(f"on_channel_post failed: {e}")

        app.add_handler(MessageHandler(filters.ChatType.CHANNEL, on_channel_post))
        self._app = app

    def start(self, backend_loop: asyncio.AbstractEventLoop):
        self._loop = backend_loop

        def run():
            asyncio.set_event_loop(asyncio.new_event_loop())
            while True:
                try:
                    if not self._app:
                        self._build_app()
                    logger.info("Telegram polling starting…")
                    self._app.run_polling(
                        allowed_updates=["channel_post"],
                        drop_pending_updates=True,
                        stop_signals=None,
                        bootstrap_retries=10,
                    )
                    logger.info("Telegram polling stopped gracefully.")
                    break
                except Exception as e:
                    logger.exception(
                        f"Polling error: {type(e).__name__}: {e} — retry in {RETRY_DELAY_SECONDS}s"
                    )
                    time.sleep(RETRY_DELAY_SECONDS)

        th = threading.Thread(target=run, daemon=True)
        th.start()
        logger.info("Telegram polling thread started.")


# ===== Messenger =====
class TelegramMessenger:
    def __init__(self, bot_token: str, target_group_id: int):
        self._bot = Bot(token=bot_token, request=_build_httpx_request_from_env())
        self._target_group_id = target_group_id
        logger.info(f"TelegramMessenger initialized for chat_id={target_group_id}")

    async def send_text_with_button(
        self,
        text: str,
        orderRate: Any = None,
        flag: Any = None,
        inline_json: Optional[Dict[str, Any]] = None,
        ai_json: Optional[Dict[str, Any]] = None,
    ):
        """
        1. תמיד שולח את ההודעה המלאה ל-TARGET_GROUP_ID (ללא כפתורים).
        2. אם flag == True ויש UsersGroupChat:
           שולח ל-UsersGroupChat הודעה מסוכמת:
           - שם החברה
           - סימבול ת״א
           - סימבול ארה״ב
           - פרטי orderRate (ENTRY/SL/TP) בצורה יפה
        """

        # 1) שליחה ראשית לקבוצת היעד
        try:
            await self._bot.send_message(
                chat_id=self._target_group_id,
                text=text,
            )
            logger.info("Message sent to target group (no buttons).")
        except Exception as e:
            logger.exception(
                f"send_text_with_button to target_group failed: {e}"
            )

        # 2) שליחה מסוכמת ל-UsersGroupChat לפי flag
        try:
            is_true_flag = bool(flag)
            logger.info("flag evaluated as: %s", is_true_flag)

            if is_true_flag and UsersGroupChat:
                company, tase, us = _extract_ai_fields_from_text(text)

                extra_lines: List[str] = []

                if company:
                    extra_lines.append(f"שם החברה: {company}")
                if tase:
                    extra_lines.append(f"סימבול ת״א: {tase}")
                if us:
                    extra_lines.append(f"סימבול ארה״ב: {us}")

                # הצגה יפה של orderRate אם קיים
                if isinstance(orderRate, dict):
                    entry = orderRate.get("ENTRY_PRICE")
                    sl = orderRate.get("STOP_LOSS")
                    tp = orderRate.get("TAKE_PROFIT")

                    if entry is not None or sl is not None or tp is not None:
                        extra_lines.append("")
                        extra_lines.append("פרטי עסקה):")
                        if entry is not None:
                            extra_lines.append(f"מחיר כניסה: {entry}")
                        if sl is not None:
                            extra_lines.append(f"סטופ לוס: {sl}")
                        if tp is not None:
                            extra_lines.append(f"טייק פרופיט: {tp}")

                # אם אין כלום, לא נשלח סתם הודעה ריקה
                if not extra_lines:
                    logger.info(
                        "flag=True אך לא נמצאו נתונים להרכבת הודעת UsersGroupChat."
                    )
                    return

                extra_text = "\n".join(extra_lines)

                await self._bot.send_message(
                    chat_id=UsersGroupChat,
                    text=extra_text,
                )
                logger.info(
                    "Extra message sent to UsersGroupChat due to flag=True."
                )
            else:
                logger.info(
                    "No extra message sent to UsersGroupChat (flag=%s, UsersGroupChat=%s)",
                    flag,
                    UsersGroupChat,
                )

        except Exception as e:
            logger.exception(
                f"send_text_with_button extra-message logic failed: {e}"
            )
