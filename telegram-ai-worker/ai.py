from __future__ import annotations

import os
import re
import tempfile
from typing import List, Optional
from urllib.parse import urlparse
from html.parser import HTMLParser

import requests
from requests.exceptions import RequestException, Timeout, HTTPError, ConnectionError
from dotenv import load_dotenv
from openai import OpenAI

from log_utils import build_logger

# Optional converters (lazy import flags)
_HAS_PDFKIT = False
_HAS_WEASYPRINT = False
try:
    import pdfkit  # requires wkhtmltopdf installed on the machine
    _HAS_PDFKIT = True
except Exception as e:
    _HAS_PDFKIT = False

try:
    from weasyprint import HTML as WEASY_HTML  # pure-Python renderer (Cairo dependencies)
    _HAS_WEASYPRINT = True
except Exception as e:
    _HAS_WEASYPRINT = False

# Load environment and initialize client
load_dotenv()
logger = build_logger("ai")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------------------------
# Utilities
# ---------------------------

def _is_url(s: str) -> bool:
    try:
        u = urlparse(s)
        return u.scheme in ("http", "https") and bool(u.netloc)
    except Exception as e:
        logger.exception(f"_is_url failed: {e}")
        return False

class _LightHTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._chunks: List[str] = []

    def handle_data(self, data):
        if data and not data.isspace():
            self._chunks.append(data.strip())

    def text(self) -> str:
        t = " ".join(self._chunks)
        return re.sub(r"\s+", " ", t).strip()

def _html_to_text(html: str) -> str:
    p = _LightHTMLTextExtractor()
    try:
        p.feed(html)
    except Exception as e:
        logger.exception(f"_html_to_text parse failed: {e}")
    return p.text()

def _download_bytes(url: str, timeout: int = 120) -> tuple[bytes, str]:
    """
    Downloads a URL and returns (content_bytes, content_type_lower).
    """
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        ct = (r.headers.get("Content-Type") or "").lower()
        logger.info(f"_download_bytes OK url={url} ct='{ct}' size={len(r.content)}")
        return r.content, ct
    except (Timeout, HTTPError, ConnectionError, RequestException) as e:
        logger.exception(f"_download_bytes failed for {url}: {e}")
        raise

def _head_content_type(url: str, timeout: int = 15) -> str:
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        ct = (r.headers.get("Content-Type") or "").lower()
        logger.info(f"_head_content_type url={url} -> '{ct}'")
        return ct
    except Exception as e:
        logger.warning(f"_head_content_type failed for {url}: {e}")
        return ""

def _save_bytes_to_temp_pdf(data: bytes) -> str:
    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    logger.info(f"Saved temp PDF: {tmp_path} ({len(data)} bytes)")
    return tmp_path

def _save_text_to_temp_html(html: str) -> str:
    fd, tmp_path = tempfile.mkstemp(suffix=".html")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"Saved temp HTML: {tmp_path} (len={len(html)})")
    return tmp_path

def _convert_html_str_to_pdf_file(html_str: str) -> Optional[str]:
    """
    Try to convert an HTML string to a temporary PDF file.
    Preference: pdfkit (wkhtmltopdf), fallback: WeasyPrint.
    Returns local PDF path or None if conversion not possible.
    """
    if _HAS_PDFKIT:
        try:
            out_fd, out_pdf = tempfile.mkstemp(suffix=".pdf")
            os.close(out_fd)
            html_path = _save_text_to_temp_html(html_str)
            import pdfkit  # type: ignore
            pdfkit.from_file(html_path, out_pdf)
            try:
                os.remove(html_path)
            except Exception:
                pass
            logger.info(f"Converted HTML->PDF using pdfkit: {out_pdf}")
            return out_pdf
        except Exception as e:
            logger.exception(f"pdfkit conversion failed: {e}")

    if _HAS_WEASYPRINT:
        try:
            out_fd, out_pdf = tempfile.mkstemp(suffix=".pdf")
            os.close(out_fd)
            from weasyprint import HTML as WEASY_HTML  # type: ignore
            WEASY_HTML(string=html_str).write_pdf(out_pdf)
            logger.info(f"Converted HTML->PDF using WeasyPrint: {out_pdf}")
            return out_pdf
        except Exception as e:
            logger.exception(f"WeasyPrint conversion failed: {e}")

    logger.warning("No HTML->PDF converter available; will fall back to text.")
    return None

def _convert_local_html_file_to_pdf_file(html_path: str) -> Optional[str]:
    try:
        with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
            html_str = f.read()
        logger.info(f"Read local HTML file: {html_path} (len={len(html_str)})")
    except Exception as e:
        logger.exception(f"read local HTML failed: {e}")
        return None
    return _convert_html_str_to_pdf_file(html_str)

def _is_probably_html_by_url(url: str, content_type: str) -> bool:
    url_l = url.lower()
    return url_l.endswith((".html", ".htm")) or ("text/html" in content_type)

def _is_probably_pdf_by_url(url: str, content_type: str) -> bool:
    url_l = url.lower()
    return url_l.endswith(".pdf") or ("application/pdf" in content_type)

# ---------------------------
# Unified function
# ---------------------------
def ask_with_sources(
    system_prompt: str = None,
    question: str = None,
    sources: List[str] | None = None,
    model: str = "gpt-5",
    max_inline_chars: int = 40000,
) -> str:
    """
    Unified function:
      - Uses PROMPT and QUESTION from .env if not provided.
      - Sends either QUESTION or just documents.
      - Auto-converts HTML/HTM (remote/local) to PDF when possible,
        otherwise falls back to cleaned text.
      - All steps are logged; errors raise exceptions with context.
    """
    sources = sources or []

    # Load from env if not passed (preserve your current behavior)
    system_prompt = os.getenv("PROMPT")
    question = os.getenv("QUESTION")

    if not system_prompt:
        logger.error("Missing PROMPT from environment or argument.")
        raise ValueError("Missing PROMPT from environment or argument.")

    content_items: List[dict] = []
    temps_to_cleanup: List[str] = []

    if question:
        content_items.append({"type": "input_text", "text": question})
        logger.info("Added QUESTION text to content_items.")

    try:
        for s in sources:
            logger.info(f"Processing source: {s}")
            if _is_url(s):
                # HEAD for quick CT
                ct_head = _head_content_type(s)
                is_pdf = _is_probably_pdf_by_url(s, ct_head)
                is_html = _is_probably_html_by_url(s, ct_head)

                if not (is_pdf or is_html):
                    # GET and decide
                    try:
                        data, ct_get = _download_bytes(s, timeout=30)
                        if _is_probably_pdf_by_url(s, ct_get):
                            tmp_pdf = _save_bytes_to_temp_pdf(data)
                            temps_to_cleanup.append(tmp_pdf)
                            with open(tmp_pdf, "rb") as f:
                                uploaded = client.files.create(file=f, purpose="assistants")
                            content_items.append({"type": "input_file", "file_id": uploaded.id})
                            logger.info(f"Uploaded remote PDF (by GET) for {s}")
                            continue
                        elif _is_probably_html_by_url(s, ct_get):
                            html_str = data.decode("utf-8", errors="ignore")
                            pdf_path = _convert_html_str_to_pdf_file(html_str)
                            if pdf_path:
                                temps_to_cleanup.append(pdf_path)
                                with open(pdf_path, "rb") as f:
                                    uploaded = client.files.create(file=f, purpose="assistants")
                                content_items.append({"type": "input_file", "file_id": uploaded.id})
                                logger.info(f"Uploaded converted HTML->PDF (by GET) for {s}")
                            else:
                                text = _html_to_text(html_str)
                                if len(text) > max_inline_chars:
                                    text = text[:max_inline_chars] + "\n...[truncated]..."
                                content_items.append({"type": "input_text", "text": f"[SOURCE: {s}]\n{text}"})
                                logger.info(f"Sent HTML as cleaned text (no converter) for {s}")
                            continue
                        else:
                            text = data.decode("utf-8", errors="ignore")
                            if len(text) > max_inline_chars:
                                text = text[:max_inline_chars] + "\n...[truncated]..."
                            content_items.append({"type": "input_text", "text": f"[SOURCE: {s}]\n{text}"})
                            logger.info(f"Sent unknown content as text for {s}")
                            continue
                    except Exception as e:
                        logger.exception(f"GET fallback path failed for {s}: {e}")

                # HEAD-informed path
                try:
                    if is_pdf:
                        data, _ = _download_bytes(s, timeout=30)
                        tmp_pdf = _save_bytes_to_temp_pdf(data)
                        temps_to_cleanup.append(tmp_pdf)
                        with open(tmp_pdf, "rb") as f:
                            uploaded = client.files.create(file=f, purpose="assistants")
                        content_items.append({"type": "input_file", "file_id": uploaded.id})
                        logger.info(f"Uploaded remote PDF (via HEAD): {s}")
                    elif is_html:
                        data, _ = _download_bytes(s, timeout=30)
                        html_str = data.decode("utf-8", errors="ignore")
                        pdf_path = _convert_html_str_to_pdf_file(html_str)
                        if pdf_path:
                            temps_to_cleanup.append(pdf_path)
                            with open(pdf_path, "rb") as f:
                                uploaded = client.files.create(file=f, purpose="assistants")
                            content_items.append({"type": "input_file", "file_id": uploaded.id})
                            logger.info(f"Uploaded converted HTML->PDF (via HEAD): {s}")
                        else:
                            text = _html_to_text(html_str)
                            if len(text) > max_inline_chars:
                                text = text[:max_inline_chars] + "\n...[truncated]..."
                            content_items.append({"type": "input_text", "text": f"[SOURCE: {s}]\n{text}"})
                            logger.info(f"Sent HTML as cleaned text (no converter available) for {s}")
                except Exception as e:
                    logger.exception(f"HEAD-informed path failed for {s}: {e}")
            else:
                # Local file
                if not os.path.exists(s):
                    logger.error(f"Local source not found: {s}")
                    raise FileNotFoundError(f"Source not found: {s}")

                sl = s.lower()
                if sl.endswith(".pdf"):
                    try:
                        with open(s, "rb") as f:
                            uploaded = client.files.create(file=f, purpose="assistants")
                        content_items.append({"type": "input_file", "file_id": uploaded.id})
                        logger.info(f"Uploaded local PDF: {s}")
                    except Exception as e:
                        logger.exception(f"Upload local PDF failed ({s}): {e}")
                        raise
                elif sl.endswith((".html", ".htm")):
                    pdf_path = _convert_local_html_file_to_pdf_file(s)
                    if pdf_path:
                        temps_to_cleanup.append(pdf_path)
                        try:
                            with open(pdf_path, "rb") as f:
                                uploaded = client.files.create(file=f, purpose="assistants")
                            content_items.append({"type": "input_file", "file_id": uploaded.id})
                            logger.info(f"Uploaded converted local HTML->PDF: {s}")
                        except Exception as e:
                            logger.exception(f"Upload converted local HTML->PDF failed ({s}): {e}")
                            raise
                    else:
                        try:
                            with open(s, "r", encoding="utf-8", errors="ignore") as f:
                                raw_html = f.read()
                            text = _html_to_text(raw_html)
                            if len(text) > max_inline_chars:
                                text = text[:max_inline_chars] + "\n...[truncated]..."
                            content_items.append({"type": "input_text", "text": f"[SOURCE: {s}]\n{text}"})
                            logger.info(f"Sent local HTML as cleaned text (no converter): {s}")
                        except Exception as e:
                            logger.exception(f"Read local HTML as text failed ({s}): {e}")
                            raise
                else:
                    # Any other local text file
                    try:
                        with open(s, "r", encoding="utf-8", errors="ignore") as f:
                            raw = f.read()
                        if len(raw) > max_inline_chars:
                            raw = raw[:max_inline_chars] + "\n...[truncated]..."
                        content_items.append({"type": "input_text", "text": f"[SOURCE: {s}]\n{raw}"})
                        logger.info(f"Sent local text file: {s}")
                    except Exception as e:
                        logger.exception(f"Read local text file failed ({s}): {e}")
                        raise

        if not content_items:
            logger.error("No content to send to GPT. Provide either QUESTION or source files/URLs.")
            raise ValueError("No content to send to GPT. Provide either QUESTION or source files/URLs.")

        content = [{"role": "user", "content": content_items}]
        logger.info(f"Prepared {len(content_items)} content items. Sending to model='{model}'…")

        try:
            resp = client.responses.create(
                model=model,
                instructions=system_prompt.strip(),
                input=content
            )
            out = resp.output_text
            logger.info(f"Model response received. length={len(out)}")
            # Also log the first 500 chars for quick peek
            logger.debug(f"Model response preview: {out[:500]}")
            return out
        except Exception as e:
            logger.exception(f"OpenAI responses.create failed: {e}")
            raise
    finally:
        for p in temps_to_cleanup:
            try:
                os.remove(p)
                logger.info(f"Cleaned temp file: {p}")
            except Exception as e:
                logger.warning(f"Failed to remove temp file '{p}': {e}")
