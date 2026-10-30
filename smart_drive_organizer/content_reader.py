from __future__ import annotations

import re
import zipfile
from email import policy
from email.parser import BytesParser
from html import unescape
from pathlib import Path
import sys

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


def _legacy_office_text(path: Path, kind: str) -> str:
    """Read binary .doc/.xls/.ppt files through installed desktop Office, when available.

    Uses a separate hidden Office process, opens files read-only, disables macro
    automation and external workbook link updates, and always closes the document.
    No Office installation is downloaded or changed.
    """
    if sys.platform != "win32":
        return ""
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return ""

    pythoncom.CoInitialize()
    application = None
    document = None
    pieces: list[str] = []
    total = 0
    try:
        if kind == "word":
            application = win32com.client.DispatchEx("Word.Application")
            application.Visible = False
            application.DisplayAlerts = 0
            application.AutomationSecurity = 3
            document = application.Documents.Open(
                FileName=str(path), ConfirmConversions=False, ReadOnly=True,
                AddToRecentFiles=False, Revert=False, NoEncodingDialog=True,
                OpenAndRepair=True,
            )
            value = str(document.Content.Text or "")
            return value[:MAX_TEXT_CHARS]

        if kind == "excel":
            application = win32com.client.DispatchEx("Excel.Application")
            application.Visible = False
            application.DisplayAlerts = False
            application.AutomationSecurity = 3
            application.EnableEvents = False
            application.AskToUpdateLinks = False
            document = application.Workbooks.Open(
                Filename=str(path), UpdateLinks=0, ReadOnly=True,
                AddToMru=False, IgnoreReadOnlyRecommended=True,
            )
            sheet_count = min(int(document.Worksheets.Count), 30)
            for sheet_index in range(1, sheet_count + 1):
                sheet = document.Worksheets(sheet_index)
                used = sheet.UsedRange
                values = used.Value
                if values is None:
                    continue
                if not isinstance(values, tuple):
                    values = ((values,),)
                for row in values[:2000]:
                    cells = row if isinstance(row, tuple) else (row,)
                    line = " ".join(str(value) for value in cells if value is not None)
                    if line:
                        pieces.append(line)
                        total += len(line)
                    if total >= MAX_TEXT_CHARS:
                        break
                if total >= MAX_TEXT_CHARS:
                    break
            return " ".join(pieces)[:MAX_TEXT_CHARS]

        if kind == "powerpoint":
            application = win32com.client.DispatchEx("PowerPoint.Application")
            application.DisplayAlerts = 1
            document = application.Presentations.Open(
                str(path), ReadOnly=True, Untitled=False, WithWindow=False,
            )
            slide_count = min(int(document.Slides.Count), 250)
            for slide_index in range(1, slide_count + 1):
                slide = document.Slides(slide_index)
                for shape_index in range(1, int(slide.Shapes.Count) + 1):
                    shape = slide.Shapes(shape_index)
                    try:
                        if shape.HasTextFrame and shape.TextFrame.HasText:
                            value = str(shape.TextFrame.TextRange.Text or "")
                            pieces.append(value)
                            total += len(value)
                    except Exception:
                        continue
                    if total >= MAX_TEXT_CHARS:
                        break
                if total >= MAX_TEXT_CHARS:
                    break
            return " ".join(pieces)[:MAX_TEXT_CHARS]
        return ""
    except Exception:
        # Office is optional and may be unavailable, busy, or unable to open a
        # damaged/locked file. The metadata record can still be indexed.
        return ""
    finally:
        if document is not None:
            try:
                if kind == "word":
                    document.Close(False)
                elif kind == "excel":
                    document.Close(SaveChanges=False)
                elif kind == "powerpoint":
                    document.Close()
            except Exception:
                pass
        if application is not None:
            try:
                application.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


def read_document_text(path: Path) -> str:
    """Extract bounded searchable text locally; unsupported/locked formats return empty text."""
    suffix = path.suffix.lower()
    try:
        if path.stat().st_size > MAX_READ_BYTES:
            return ""
        if suffix in {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".log", ".yaml", ".yml", ".sql", ".tex", ".py", ".js", ".ts", ".jsx", ".tsx", ".css", ".scss", ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs", ".php", ".rb", ".sh", ".ps1", ".bat", ".cmd", ".sql", ".toml", ".ini", ".yaml", ".yml"}:
            text = _plain_text(path)
            if suffix in {".html", ".htm", ".xml"}:
                text = re.sub(r"<[^>]+>", " ", text)
            return text
        if suffix == ".rtf":
            text = _plain_text(path)
            return re.sub(r"\\[a-zA-Z]+-?\d* ?|[{}]", " ", text)[:MAX_TEXT_CHARS]
        if suffix == ".docx":
            return _docx_text(path)
        if suffix == ".doc":
            return _legacy_office_text(path, "word")
        if suffix == ".pdf":
            return _pdf_text(path)
        if suffix in {".xlsx", ".xlsm"}:
            return _xlsx_text(path)
        if suffix == ".xls":
            return _legacy_office_text(path, "excel")
        if suffix == ".pptx":
            return _pptx_text(path)
        if suffix == ".ppt":
            return _legacy_office_text(path, "powerpoint")
        if suffix == ".eml":
            return _eml_text(path)
        if suffix == ".msg":
            return _msg_text(path)
    except (ImportError, OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError):
        return ""
    except Exception:
        # Parsers are deliberately best-effort. Bad/corrupt files remain listed
        # in the index but must not interrupt the scan of the rest of the drive.
        return ""
    return ""
