import asyncio
import os
import re
import sys
import threading
import time
from typing import Callable, List, Optional, Tuple

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest

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
            except Exception:
                pass
        elif t == "text_link" and getattr(ent, "url", None):
            cleaned = ent.url.strip().replace("\n", "")
            urls.append(cleaned)

    seen = set()
    uniq: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
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
    return HTTPXRequest(**kwargs)


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
    if text[closing + len(fence):].strip():
        return -1, -1, ""
    opening = text.rfind(fence, 0, closing)
    if opening == -1:
        return -1, -1, ""
    header = text[opening:opening + 10].lower()
    if not header.startswith("```"):
        return -1, -1, ""
    code = text[opening + len(fence):closing].strip()
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


# ===== Parse the GPT answer out of the full Telegram message text (on button click) =====

def _parse_fields_from_full_message(full_text: str) -> Optional[str]:
    """
    מקבל את מלל ההודעה שנשלחה עם תשובת ה-AI (כולל "כותרת ההודעה:", "קישור שצורף:", "תשובה מ-AI:", ...).
    מאתר את הקטע שאחרי "תשובה מ-AI:" ומוציא ממנו 3 שורות:
      שם החברה: ...
      סימבול ת״א: ...
      סימבול ארה״ב: ...
    מחזיר טקסט בשלוש שורות, או None אם לא נמצאו.
    """
    if not full_text:
        return None

    anchor = "תשובה מ-AI:"
    idx = full_text.find(anchor)
    if idx == -1:
        return None
    after = full_text[idx + len(anchor):].strip()

    company = None
    tase = None
    us = None

    for line in after.splitlines():
        s = line.strip()
        if not s:
            continue

        if s.startswith("שם החברה:"):
            company = s.split(":", 1)[1].strip() or None
        elif s.startswith("סימבול ת״א:") or s.startswith("סימבול תא:") or s.startswith("סימבול ת\"א:"):
            tase = s.split(":", 1)[1].strip() or None
        elif s.startswith("סימבול ארה״ב:") or s.startswith("סימבול ארהב:") or s.startswith("סימבול ארה\"ב:"):
            us = s.split(":", 1)[1].strip() or None

        if company and tase and us:
            break

    if not (company or tase or us):
        return None

    company = company or "לא זוהה"
    tase = tase or "לא זוהה"
    us = us or "לא זוהה"

    return f"שם החברה: {company}\nסימבול ת״א: {tase}\nסימבול ארה״ב: {us}"


class TelegramListener:
    def __init__(
        self,
        bot_token: str,
        channel_id: int,
        on_urls: Callable[[List[str], str, str, str], asyncio.Future],
    ):
        self._bot_token = bot_token
        self._channel_id = channel_id
        self._on_urls = on_urls
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._request = _build_httpx_request_from_env()
        self._app = None

    def _build_app(self):
        app = (
            ApplicationBuilder()
            .token(self._bot_token)
            .request(self._request)
            .build()
        )

        async def on_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
            post = update.channel_post
            if not post or post.chat_id != self._channel_id:
                return

            text = post.text or post.caption or ""
            entities = post.entities if post.text else post.caption_entities
            ts = post.date.strftime("%Y-%m-%d %H:%M:%S")
            urls = _extract_urls(text, entities)

            print(f"[TG] {ts} - הודעה בערוץ:")
            print(text if text else "(ללא טקסט)")

            question_text = text
            link_text = ""

            if urls:
                link_text = urls[0]
                rest_urls = urls[1:]

                # הסר את ה-URLs והטקסטים של text_link
                for u in [link_text] + rest_urls:
                    question_text = question_text.replace(u, "")
                text_link_texts = []
                for ent in entities or []:
                    if getattr(ent, "type", None) == "text_link":
                        try:
                            shown = text[ent.offset: ent.offset + ent.length]
                            text_link_texts.append(shown.strip())
                        except Exception:
                            pass
                for shown in text_link_texts:
                    question_text = question_text.replace(shown, "")

                # הוצא מטריצה מסוף הטקסט
                question_text, matrix_text = _split_text_and_trailing_matrix(question_text.strip())

                print("[TG] פרטי הודעה שזוהו:")
                print(f"כותרת (question_text):\n{question_text}\n")
                print(f"קישור כללי ראשון (link_text):\n{link_text}\n")
                print(f"קישורים שנותחו להורדה (urls):\n{rest_urls}\n")
                if matrix_text:
                    print("מטריצה שזוהתה (matrix):")
                    print(matrix_text)
                    print()
                print("-" * 40)
                sys.stdout.flush()

                if self._loop and not self._loop.is_closed():
                    asyncio.run_coroutine_threadsafe(
                        self._on_urls(rest_urls, question_text, link_text, matrix_text),
                        self._loop
                    )
            else:
                q_wo_urls, matrix_text = _split_text_and_trailing_matrix(question_text.strip())
                print("[TG] לא נמצאו קישורים בהודעה.")
                if matrix_text:
                    print("מטריצה שזוהתה (matrix):")
                    print(matrix_text)
                print("-" * 40)
                sys.stdout.flush()

        async def on_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            if not query:
                return

            await query.answer()

            action_map = {
                "vote_up": "עליה",
                "vote_down": "ירידה",
                "vote_cancel": "ביטול",
            }
            action_key = (query.data or "").strip()
            action_label = action_map.get(action_key, "")

            if not action_label:
                return

            # אם מדובר בביטול – לא שולחים כלום ל-UsersGroupChat, רק מסירים כפתורים
            if action_key == "vote_cancel":
                try:
                    await query.edit_message_reply_markup(reply_markup=None)
                except Exception:
                    pass
                return

            # שלוף את הטקסט של ההודעה המקורית (זו עם התשובה והכפתורים)
            origin_text = ""
            if query.message:
                origin_text = (query.message.text or query.message.caption or "").strip()

            fields_text = _parse_fields_from_full_message(origin_text) or ""

            # בנה טקסט לשליחה ל-UsersGroupChat
            to_send = action_label
            if fields_text:
                to_send = f"{action_label}\n{fields_text}"

            if UsersGroupChat != 0:
                try:
                    await context.bot.send_message(
                        chat_id=UsersGroupChat,
                        text=to_send
                    )
                except Exception as e:
                    print(f"[TG] send action label error: {type(e).__name__}: {e}", file=sys.stderr)

            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass

        app.add_handler(MessageHandler(filters.ChatType.CHANNEL, on_channel_post))
        app.add_handler(CallbackQueryHandler(on_button_click))
        self._app = app

    def start(self, backend_loop: asyncio.AbstractEventLoop):
        self._loop = backend_loop

        def run():
            asyncio.set_event_loop(asyncio.new_event_loop())
            while True:
                try:
                    if not self._app:
                        self._build_app()
                    print("[TG] Telegram polling starting...")
                    self._app.run_polling(
                        allowed_updates=["channel_post", "callback_query"],
                        drop_pending_updates=True,
                        stop_signals=None,
                        bootstrap_retries=10,
                    )
                    print("[TG] Telegram polling stopped gracefully.")
                    break
                except Exception as e:
                    print(
                        f"[TG] polling error: {type(e).__name__}: {e} — retry in {RETRY_DELAY_SECONDS}s",
                        file=sys.stderr,
                    )
                    sys.stderr.flush()
                    time.sleep(RETRY_DELAY_SECONDS)

        th = threading.Thread(target=run, daemon=True)
        th.start()
        print("[TG] Telegram polling thread started.")


class TelegramMessenger:
    def __init__(self, bot_token: str, target_group_id: int):
        self._bot = Bot(token=bot_token, request=_build_httpx_request_from_env())
        self._target_group_id = target_group_id

    async def send_text_with_button(self, text: str):
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("עליה", callback_data="vote_up"),
                InlineKeyboardButton("ירידה", callback_data="vote_down"),
                InlineKeyboardButton("ביטול", callback_data="vote_cancel"),
            ]
        ])
        try:
            await self._bot.send_message(
                chat_id=self._target_group_id,
                text=text,
                reply_markup=keyboard,
            )
        except Exception as e:
            print(f"[TG] send_text_with_button error: {type(e).__name__}: {e}", file=sys.stderr)
