from __future__ import annotations

import email
import re
import zipfile
from email import policy
from email.parser import BytesParser
from html import unescape
from pathlib import Path

MAX_READ_BYTES = 64 * 1024 * 1024
MAX_TEXT_CHARS = 250_000


def _read_bytes(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(MAX_READ_BYTES + 1)[:MAX_READ_BYTES]


def _plain_text(path: Path) -> str:
    data = _read_bytes(path)
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding, errors="ignore")[:MAX_TEXT_CHARS]
        except (LookupError, UnicodeError):
            continue
    return ""


def _docx_text(path: Path) -> str:
    from xml.etree import ElementTree as ET
    pieces = []
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist()
                 if name.startswith("word/") and name.endswith(".xml")
                 and any(part in name for part in ("document.xml", "header", "footer", "footnotes", "endnotes", "comments"))]
        for name in names:
            root = ET.fromstring(archive.read(name))
            pieces.extend(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
            if sum(map(len, pieces)) >= MAX_TEXT_CHARS:
                break
    return " ".join(pieces)[:MAX_TEXT_CHARS]


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path), strict=False)
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                return ""
        except Exception:
            return ""
    pieces = []
    for page in reader.pages[:250]:
        try:
            pieces.append(page.extract_text() or "")
        except Exception:
            continue
        if sum(map(len, pieces)) >= MAX_TEXT_CHARS:
            break
    return " ".join(pieces)[:MAX_TEXT_CHARS]


def _xlsx_text(path: Path) -> str:
    from openpyxl import load_workbook
    workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    pieces = []
    total = 0
    try:
        for sheet in workbook.worksheets[:30]:
            for row in sheet.iter_rows(max_row=2000, max_col=40, values_only=True):
                values = [str(value) for value in row if value is not None]
                if values:
                    line = " ".join(values)
                    pieces.append(line)
                    total += len(line)
                if total >= MAX_TEXT_CHARS:
                    break
            if total >= MAX_TEXT_CHARS:
                break
    finally:
        workbook.close()
    return " ".join(pieces)[:MAX_TEXT_CHARS]


def _pptx_text(path: Path) -> str:
    from pptx import Presentation
    presentation = Presentation(str(path))
    pieces = []
    total = 0
    for slide in presentation.slides[:250]:
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                pieces.append(shape.text)
                total += len(shape.text)
            if total >= MAX_TEXT_CHARS:
                break
        if total >= MAX_TEXT_CHARS:
            break
    return " ".join(pieces)[:MAX_TEXT_CHARS]


def _eml_text(path: Path) -> str:
    message = BytesParser(policy=policy.default).parsebytes(_read_bytes(path))
    pieces = []
    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() not in {"text/plain", "text/html"}:
            continue
        try:
            value = part.get_content()
        except (LookupError, UnicodeError, AttributeError):
            payload = part.get_payload(decode=True) or b""
            value = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if isinstance(value, str):
            if part.get_content_type() == "text/html":
                value = re.sub(r"<[^>]+>", " ", unescape(value))
            pieces.append(value)
        if sum(map(len, pieces)) >= MAX_TEXT_CHARS:
            break
    headers = " ".join(str(message.get(key, "")) for key in ("subject", "from", "to", "cc"))
    return (headers + " " + " ".join(pieces))[:MAX_TEXT_CHARS]


def _msg_text(path: Path) -> str:
    # Optional parser: if extract-msg is unavailable, the filename remains indexed.
    import extract_msg
    message = extract_msg.Message(str(path))
    try:
        return " ".join(str(value or "") for value in (
            message.subject, message.sender, message.to, message.cc, message.body
        ))[:MAX_TEXT_CHARS]
    finally:
        message.close()


def read_document_text(path: Path) -> str:
    """Extract bounded searchable text locally; unsupported/locked formats return empty text."""
    suffix = path.suffix.lower()
    try:
        if suffix in {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".log", ".yaml", ".yml", ".sql", ".tex", ".py", ".js", ".ts", ".css", ".ps1", ".bat", ".cmd"}:
            text = _plain_text(path)
            if suffix in {".html", ".htm", ".xml"}:
                text = re.sub(r"<[^>]+>", " ", text)
            return text
        if suffix == ".rtf":
            text = _plain_text(path)
            return re.sub(r"\\[a-zA-Z]+-?\d* ?|[{}]", " ", text)[:MAX_TEXT_CHARS]
        if suffix == ".docx":
            return _docx_text(path)
        if suffix == ".pdf":
            return _pdf_text(path)
        if suffix in {".xlsx", ".xlsm"}:
            return _xlsx_text(path)
        if suffix == ".pptx":
            return _pptx_text(path)
        if suffix == ".eml":
            return _eml_text(path)
        if suffix == ".msg":
            return _msg_text(path)
    except (ImportError, OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError, email.errors.MessageError):
        return ""
    except Exception:
        # Parsers are deliberately best-effort. Bad/corrupt files remain listed
        # in the index but must not interrupt the scan of the rest of the drive.
        return ""
    return ""
