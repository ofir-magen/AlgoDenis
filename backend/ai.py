# ai.py
from __future__ import annotations

import os
import re
import tempfile
from typing import List, Optional
from urllib.parse import urlparse
from html.parser import HTMLParser

import requests
from dotenv import load_dotenv
from openai import OpenAI

# Optional converters (lazy import flags)
_HAS_PDFKIT = False
_HAS_WEASYPRINT = False
try:
    import pdfkit  # requires wkhtmltopdf installed on the machine
    _HAS_PDFKIT = True
except Exception:
    _HAS_PDFKIT = False

try:
    from weasyprint import HTML as WEASY_HTML  # pure-Python renderer (Cairo dependencies)
    _HAS_WEASYPRINT = True
except Exception:
    _HAS_WEASYPRINT = False

# Load environment and initialize client
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------------------------
# Utilities
# ---------------------------

def _is_url(s: str) -> bool:
    try:
        u = urlparse(s)
        return u.scheme in ("http", "https") and bool(u.netloc)
    except Exception:
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
    p.feed(html)
    return p.text()

def _download_bytes(url: str, timeout: int = 30) -> tuple[bytes, str]:
    """
    Downloads a URL and returns (content_bytes, content_type_lower).
    """
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    ct = (r.headers.get("Content-Type") or "").lower()
    return r.content, ct

def _head_content_type(url: str, timeout: int = 15) -> str:
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        return (r.headers.get("Content-Type") or "").lower()
    except Exception:
        return ""

def _save_bytes_to_temp_pdf(data: bytes) -> str:
    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return tmp_path

def _save_text_to_temp_html(html: str) -> str:
    fd, tmp_path = tempfile.mkstemp(suffix=".html")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)
    return tmp_path

def _convert_html_str_to_pdf_file(html_str: str) -> Optional[str]:
    """
    Try to convert an HTML string to a temporary PDF file.
    Preference: pdfkit (wkhtmltopdf), fallback: WeasyPrint.
    Returns local PDF path or None if conversion not possible.
    """
    # pdfkit path
    if _HAS_PDFKIT:
        try:
            out_fd, out_pdf = tempfile.mkstemp(suffix=".pdf")
            os.close(out_fd)  # pdfkit writes to the path
            # Write html to temp file for more stable conversion with pdfkit
            html_path = _save_text_to_temp_html(html_str)
            pdfkit.from_file(html_path, out_pdf)
            try:
                os.remove(html_path)
            except Exception:
                pass
            return out_pdf
        except Exception as e:
            print(f"[ai] pdfkit conversion failed: {type(e).__name__}: {e}")

    # WeasyPrint path
    if _HAS_WEASYPRINT:
        try:
            out_fd, out_pdf = tempfile.mkstemp(suffix=".pdf")
            os.close(out_fd)
            WEASY_HTML(string=html_str).write_pdf(out_pdf)
            return out_pdf
        except Exception as e:
            print(f"[ai] WeasyPrint conversion failed: {type(e).__name__}: {e}")

    # If both failed/unavailable
    return None

def _convert_local_html_file_to_pdf_file(html_path: str) -> Optional[str]:
    """
    Convert a local HTML file to a temporary PDF file (same strategy).
    Returns PDF path or None.
    """
    try:
        with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
            html_str = f.read()
    except Exception as e:
        print(f"[ai] read local HTML failed: {e}")
        return None
    return _convert_html_str_to_pdf_file(html_str)

def _is_probably_html_by_url(url: str, content_type: str) -> bool:
    """
    Decide if a URL is HTML (including .htm) based on suffix or content-type.
    """
    url_l = url.lower()
    if url_l.endswith(".html") or url_l.endswith(".htm"):
        return True
    if "text/html" in content_type:
        return True
    return False

def _is_probably_pdf_by_url(url: str, content_type: str) -> bool:
    url_l = url.lower()
    if url_l.endswith(".pdf"):
        return True
    if "application/pdf" in content_type:
        return True
    return False

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
      - New: auto-converts HTML/HTM (remote/local) to PDF whenever possible,
        so it flows through the existing 'input_file' path.
        If conversion isn't possible, falls back to sending cleaned text.
    """
    sources = sources or []

    # Load from env if not passed (preserve your current behavior)
    system_prompt = os.getenv("PROMPT")
    question = os.getenv("QUESTION")

    if not system_prompt:
        raise ValueError("Missing PROMPT from environment or argument.")

    content_items: List[dict] = []
    temps_to_cleanup: List[str] = []

    if question:
        content_items.append({"type": "input_text", "text": question})

    try:
        for s in sources:
            # URL source
            if _is_url(s):
                # First, try HEAD to quickly guess content-type
                ct_head = _head_content_type(s)
                is_pdf = _is_probably_pdf_by_url(s, ct_head)
                is_html = _is_probably_html_by_url(s, ct_head)

                # If can't tell from HEAD, we'll GET and decide
                if not (is_pdf or is_html):
                    try:
                        data, ct_get = _download_bytes(s, timeout=30)
                        if _is_probably_pdf_by_url(s, ct_get):
                            # Save PDF as-is
                            tmp_pdf = _save_bytes_to_temp_pdf(data)
                            temps_to_cleanup.append(tmp_pdf)
                            with open(tmp_pdf, "rb") as f:
                                uploaded = client.files.create(file=f, purpose="assistants")
                            content_items.append({"type": "input_file", "file_id": uploaded.id})
                            print(f"[ai] Uploaded remote PDF (detected via GET): {s}")
                            continue
                        elif _is_probably_html_by_url(s, ct_get):
                            # Convert HTML bytes -> PDF if possible
                            html_str = data.decode("utf-8", errors="ignore")
                            pdf_path = _convert_html_str_to_pdf_file(html_str)
                            if pdf_path:
                                temps_to_cleanup.append(pdf_path)
                                with open(pdf_path, "rb") as f:
                                    uploaded = client.files.create(file=f, purpose="assistants")
                                content_items.append({"type": "input_file", "file_id": uploaded.id})
                                print(f"[ai] Uploaded converted HTML->PDF (via GET): {s}")
                            else:
                                # Fallback to text
                                text = _html_to_text(html_str)
                                if len(text) > max_inline_chars:
                                    text = text[:max_inline_chars] + "\n...[truncated]..."
                                content_items.append({"type": "input_text", "text": f"[SOURCE: {s}]\n{text}"})
                                print(f"[ai] Sent HTML as cleaned text (no converter available): {s}")
                            continue
                        else:
                            # Unknown type, treat as text
                            text = data.decode("utf-8", errors="ignore")
                            if len(text) > max_inline_chars:
                                text = text[:max_inline_chars] + "\n...[truncated]..."
                            content_items.append({"type": "input_text", "text": f"[SOURCE: {s}]\n{text}"})
                            print(f"[ai] Sent unknown content as text: {s}")
                            continue
                    except Exception as e:
                        print(f"[ai] GET fallback failed for {s}: {e}. Will try simple GET->text next.")

                # If we could tell from HEAD:
                if is_pdf:
                    # Download PDF and upload
                    data, _ = _download_bytes(s, timeout=30)
                    tmp_pdf = _save_bytes_to_temp_pdf(data)
                    temps_to_cleanup.append(tmp_pdf)
                    with open(tmp_pdf, "rb") as f:
                        uploaded = client.files.create(file=f, purpose="assistants")
                    content_items.append({"type": "input_file", "file_id": uploaded.id})
                    print(f"[ai] Uploaded remote PDF (via HEAD detection): {s}")
                elif is_html:
                    # Download, then try to convert HTML -> PDF
                    data, _ = _download_bytes(s, timeout=30)
                    html_str = data.decode("utf-8", errors="ignore")
                    pdf_path = _convert_html_str_to_pdf_file(html_str)
                    if pdf_path:
                        temps_to_cleanup.append(pdf_path)
                        with open(pdf_path, "rb") as f:
                            uploaded = client.files.create(file=f, purpose="assistants")
                        content_items.append({"type": "input_file", "file_id": uploaded.id})
                        print(f"[ai] Uploaded converted HTML->PDF (via HEAD detection): {s}")
                    else:
                        # Fallback to sending cleaned text
                        text = _html_to_text(html_str)
                        if len(text) > max_inline_chars:
                            text = text[:max_inline_chars] + "\n...[truncated]..."
                        content_items.append({"type": "input_text", "text": f"[SOURCE: {s}]\n{text}"})
                        print(f"[ai] Sent HTML as cleaned text (no converter available): {s}")

            # Local file source
            else:
                if not os.path.exists(s):
                    raise FileNotFoundError(f"Source not found: {s}")

                sl = s.lower()
                if sl.endswith(".pdf"):
                    with open(s, "rb") as f:
                        uploaded = client.files.create(file=f, purpose="assistants")
                    content_items.append({"type": "input_file", "file_id": uploaded.id})
                    print(f"[ai] Uploaded local PDF: {s}")

                elif sl.endswith(".html") or sl.endswith(".htm"):
                    # Try to convert local HTML -> PDF
                    pdf_path = _convert_local_html_file_to_pdf_file(s)
                    if pdf_path:
                        temps_to_cleanup.append(pdf_path)
                        with open(pdf_path, "rb") as f:
                            uploaded = client.files.create(file=f, purpose="assistants")
                        content_items.append({"type": "input_file", "file_id": uploaded.id})
                        print(f"[ai] Uploaded converted local HTML->PDF: {s}")
                    else:
                        # Fallback to cleaned text
                        with open(s, "r", encoding="utf-8", errors="ignore") as f:
                            raw_html = f.read()
                        text = _html_to_text(raw_html)
                        if len(text) > max_inline_chars:
                            text = text[:max_inline_chars] + "\n...[truncated]..."
                        content_items.append({"type": "input_text", "text": f"[SOURCE: {s}]\n{text}"})
                        print(f"[ai] Sent local HTML as cleaned text (no converter available): {s}")

                else:
                    # Any other local text file
                    with open(s, "r", encoding="utf-8", errors="ignore") as f:
                        raw = f.read()
                    if len(raw) > max_inline_chars:
                        raw = raw[:max_inline_chars] + "\n...[truncated]..."
                    content_items.append({"type": "input_text", "text": f"[SOURCE: {s}]\n{raw}"})
                    print(f"[ai] Sent local text file: {s}")

        if not content_items:
            raise ValueError("No content to send to GPT. Provide either QUESTION or source files/URLs.")

        content = [{"role": "user", "content": content_items}]
        print(f"[ai] Prepared {len(content_items)} content items. Sending to model...")

        resp = client.responses.create(
            model=model,
            instructions=system_prompt.strip(),
            input=content
        )
        print(resp.output_text)
        return resp.output_text

    finally:
        for p in temps_to_cleanup:
            try:
                os.remove(p)
            except Exception:
                pass
