from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from .classifier import category_for, classify_topic, load_custom_rules
from .content_reader import read_document_text
from .file_types import extension_is_selected, normalize_extension_filters
from .operation_control import OperationCancelled, OperationControl

APP_DIR_NAME = "SmartDriveOrganizer"
TEXT_CATEGORIES = {"Documents", "Code"}
DEFAULT_LIMIT = 500


def app_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    result = base / APP_DIR_NAME
    result.mkdir(parents=True, exist_ok=True)
    return result


def index_database_path() -> Path:
    return app_data_dir() / "file_search.sqlite3"


class SearchIndex:
    """Local SQLite metadata and FTS index. File contents never leave this device."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or index_database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=45)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS indexed_files (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                extension TEXT NOT NULL,
                category TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                modified_ts REAL NOT NULL,
                created_ts REAL NOT NULL,
                topic TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                text_indexed INTEGER NOT NULL DEFAULT 0,
                content_hash TEXT NOT NULL DEFAULT '',
                indexed_ts REAL NOT NULL
            )
        """)
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(indexed_files)")}
        if "text_indexed" not in columns:
            self.db.execute("ALTER TABLE indexed_files ADD COLUMN text_indexed INTEGER NOT NULL DEFAULT 0")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_files_ext ON indexed_files(extension)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_files_modified ON indexed_files(modified_ts)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_files_category ON indexed_files(category)")
        self.fts_available = True
        try:
            self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS file_fts USING fts5(name, body, location, topic, tokenize='unicode61 remove_diacritics 2')")
        except sqlite3.OperationalError:
            self.fts_available = False
        self.db.commit()

    def close(self) -> None:
        try:
            self.db.commit()
        finally:
            self.db.close()

    def needs_refresh(self, path: Path, require_text: bool = False) -> bool:
        try:
            stat = path.stat()
            row = self.db.execute(
                "SELECT size_bytes, modified_ts, text_indexed FROM indexed_files WHERE path=?",
                (str(path.resolve()),),
            ).fetchone()
            return (row is None or row["size_bytes"] != stat.st_size
                    or row["modified_ts"] != stat.st_mtime
                    or (require_text and not bool(row["text_indexed"])))
        except OSError:
            return False

    def upsert_file(self, path: Path, category: str, body: str = "", topic: str = "", text_indexed: bool = False) -> None:
        stat = path.stat()
        resolved = str(path.resolve())
        now = time.time()
        values = (
            resolved, path.name, path.suffix.lower(), category, int(stat.st_size),
            float(stat.st_mtime), float(getattr(stat, "st_ctime", stat.st_mtime)),
            topic, body[:250000], int(text_indexed), now,
        )
        old = self.db.execute("SELECT id FROM indexed_files WHERE path=?", (resolved,)).fetchone()
        if old:
            row_id = int(old["id"])
            self.db.execute("""
                UPDATE indexed_files SET name=?, extension=?, category=?, size_bytes=?,
                    modified_ts=?, created_ts=?, topic=?, body=?, text_indexed=?, indexed_ts=? WHERE id=?
            """, values[1:] + (row_id,))
        else:
            cursor = self.db.execute("""
                INSERT INTO indexed_files(path,name,extension,category,size_bytes,modified_ts,created_ts,topic,body,text_indexed,indexed_ts)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """, values)
            row_id = int(cursor.lastrowid)
        if self.fts_available:
            self.db.execute("DELETE FROM file_fts WHERE rowid=?", (row_id,))
            self.db.execute(
                "INSERT INTO file_fts(rowid,name,body,location,topic) VALUES(?,?,?,?,?)",
                (row_id, path.name, body[:250000], str(path.parent), topic),
            )

    def update_topic(self, path: Path, topic: str) -> None:
        resolved = str(path.resolve())
        row = self.db.execute(
            "SELECT id, name, body FROM indexed_files WHERE path=?", (resolved,)
        ).fetchone()
        if row is None:
            return
        row_id = int(row["id"])
        self.db.execute("UPDATE indexed_files SET topic=? WHERE id=?", (topic, row_id))
        if self.fts_available:
            self.db.execute("DELETE FROM file_fts WHERE rowid=?", (row_id,))
            self.db.execute(
                "INSERT INTO file_fts(rowid,name,body,location,topic) VALUES(?,?,?,?,?)",
                (row_id, row["name"], row["body"], str(path.parent), topic),
            )

    def refresh_classification(self, path: Path, category: str, custom_rules: Optional[list] = None) -> str:
        """Reclassify an unchanged indexed file from its saved text and current rules."""
        resolved = str(path.resolve())
        row = self.db.execute(
            "SELECT body FROM indexed_files WHERE path=?", (resolved,)
        ).fetchone()
        if row is None:
            return ""
        topic, _reason, _confidence = classify_topic(path, category, str(row["body"] or ""), custom_rules or [])
        self.update_topic(path, topic)
        return topic

    def count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0])

    def search(self, query: str = "", location: str = "", category: str = "",
               extension: str = "", topic: str = "", date_from: str = "",
               date_to: str = "", min_size_mb: str = "", max_size_mb: str = "",
               limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
        from datetime import datetime, timedelta
        from math import isfinite

        clauses: list[str] = []
        params: list[Any] = []
        join = ""
        terms = re.findall(r"[\w]+", query, flags=re.UNICODE)
        if query.strip() and not terms:
            return []
        if terms:
            if self.fts_available:
                join = " JOIN file_fts ON file_fts.rowid=indexed_files.id"
                match = " AND ".join('"' + term.replace('"', '""') + '"' for term in terms)
                clauses.append("file_fts MATCH ?")
                params.append(match)
            else:
                clauses.append("(name LIKE ? OR body LIKE ?)")
                value = "%" + query + "%"
                params.extend((value, value))
        if location.strip():
            clauses.append("path LIKE ?")
            params.append("%" + location.strip() + "%")
        if category and category != "Any":
            clauses.append("category=?")
            params.append(category)
        if extension.strip():
            ext = extension.strip().lower()
            if not ext.startswith("."):
                ext = "." + ext
            clauses.append("extension=?")
            params.append(ext)
        if topic.strip():
            clauses.append("indexed_files.topic LIKE ?")
            params.append("%" + topic.strip() + "%")

        parsed_from = None
        parsed_to = None
        try:
            if date_from.strip():
                parsed_from = datetime.strptime(date_from.strip(), "%Y-%m-%d")
            if date_to.strip():
                parsed_to = datetime.strptime(date_to.strip(), "%Y-%m-%d")
        except ValueError as error:
            raise ValueError("Dates must use YYYY-MM-DD.") from error
        if parsed_from and parsed_to and parsed_to < parsed_from:
            raise ValueError("The 'modified before' date cannot be earlier than the 'modified after' date.")
        if parsed_from:
            clauses.append("modified_ts>=?")
            params.append(time.mktime(parsed_from.timetuple()))
        if parsed_to:
            clauses.append("modified_ts<?")
            params.append(time.mktime((parsed_to + timedelta(days=1)).timetuple()))

        def parse_size(value: str, label: str) -> Optional[float]:
            if not value.strip():
                return None
            try:
                parsed = float(value)
            except ValueError as error:
                raise ValueError(f"{label} size must be a number of megabytes.") from error
            if not isfinite(parsed) or parsed < 0:
                raise ValueError(f"{label} size must be a finite non-negative number.")
            return parsed

        min_size = parse_size(min_size_mb, "Minimum")
        max_size = parse_size(max_size_mb, "Maximum")
        if min_size is not None and max_size is not None and max_size < min_size:
            raise ValueError("Maximum size cannot be smaller than minimum size.")
        if min_size is not None:
            clauses.append("size_bytes>=?")
            params.append(min_size * 1024 * 1024)
        if max_size is not None:
            clauses.append("size_bytes<=?")
            params.append(max_size * 1024 * 1024)

        sql = "SELECT indexed_files.* FROM indexed_files" + join
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY modified_ts DESC LIMIT ?"
        params.append(max(1, min(int(limit), 5000)))
        rows = self.db.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def all_records(self, limit: int = 50000) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM indexed_files ORDER BY path LIMIT ?", (max(1, min(limit, 100000)),)
        ).fetchall()
        return [dict(row) for row in rows]

    def remove_missing(self) -> int:
        rows = self.db.execute("SELECT id,path FROM indexed_files").fetchall()
        missing = [(row["id"], row["path"]) for row in rows if not Path(row["path"]).is_file()]
        for row_id, _path in missing:
            if self.fts_available:
                self.db.execute("DELETE FROM file_fts WHERE rowid=?", (row_id,))
            self.db.execute("DELETE FROM indexed_files WHERE id=?", (row_id,))
        self.db.commit()
        return len(missing)



def sync_file_operation(source: Path, destination: Path, category: str, topic: str,
                        remove_source: bool = False,
                        database: Optional[Path] = None) -> bool:
    """Keep the local search index aligned with one completed Copy or Move action."""
    target_db = database or index_database_path()
    if not target_db.exists():
        return False
    source_path = str(Path(source).expanduser().resolve())
    destination_path = Path(destination).expanduser().resolve()
    index = SearchIndex(target_db)
    try:
        row = index.db.execute(
            "SELECT category, topic, body, text_indexed FROM indexed_files WHERE path=?",
            (source_path,),
        ).fetchone()
        indexed_category = str(row["category"]) if row else category
        indexed_topic = str(topic or (row["topic"] if row else ""))
        if row:
            body = str(row["body"] or "")
            text_indexed = bool(row["text_indexed"])
        else:
            text_supported = category in TEXT_CATEGORIES
            body = read_document_text(destination_path) if text_supported else ""
            text_indexed = bool(body)

        if remove_source:
            old = index.db.execute(
                "SELECT id FROM indexed_files WHERE path=?", (source_path,)
            ).fetchone()
            if old:
                old_id = int(old["id"])
                if index.fts_available:
                    index.db.execute("DELETE FROM file_fts WHERE rowid=?", (old_id,))
                index.db.execute("DELETE FROM indexed_files WHERE id=?", (old_id,))

        index.upsert_file(destination_path, indexed_category, body, indexed_topic, text_indexed=text_indexed)
        index.db.commit()
        return True
    finally:
        index.close()


def sync_journal_actions(journal: dict, database: Optional[Path] = None) -> dict[str, int]:
    """Reflect successful manual file actions in the local search index."""
    synced = failed = 0
    for action in journal.get("actions", []):
        status = str(action.get("status", ""))
        if status not in {"copied", "moved", "copied_source_kept"}:
            continue
        try:
            synced += int(sync_file_operation(
                Path(action["source"]), Path(action["destination"]),
                str(action.get("category", "Others")), str(action.get("topic", "")),
                remove_source=(status == "moved"), database=database,
            ))
        except (KeyError, OSError, sqlite3.Error, ValueError):
            failed += 1
    return {"synced": synced, "failed": failed}


def build_index(source_roots: Iterable[Path], categories: Iterable[str],
                extension_filters: Optional[dict[str, list[str]]] = None,
                progress: Optional[Callable[[str], None]] = None,
                extract_text: bool = True,
                database: Optional[Path] = None,
                control: Optional[OperationControl] = None) -> dict[str, int]:
    """Read-only indexing of supported files using the scanner's safety exclusions."""
    from .scanner import (
        PROTECTED_DIRECTORY_NAMES, PROTECTED_FILE_EXTENSIONS,
        PROTECTED_FILE_NAMES, _is_project_root, _is_reparse_or_link,
    )
    selected = set(categories)
    filters = normalize_extension_filters(extension_filters or {})
    index = SearchIndex(database)
    rules_path = app_data_dir() / "keyword_rules.json"
    custom_rules = load_custom_rules(rules_path)
    checked = indexed = refreshed = skipped = 0
    cancelled = False
    topic_counts: dict[str, int] = {}
    seen_roots: list[Path] = []
    for source in source_roots:
        root = Path(source).expanduser().resolve()
        if not root.is_dir() or root.name.casefold() in PROTECTED_DIRECTORY_NAMES:
            skipped += 1
            continue
        if any(root == old or old in root.parents for old in seen_roots):
            continue
        seen_roots.append(root)
        def onerror(error: OSError) -> None:
            nonlocal skipped
            skipped += 1
        for current, dirs, filenames in os.walk(root, topdown=True, followlinks=False, onerror=onerror):
            if control is not None:
                try:
                    control.checkpoint()
                except OperationCancelled:
                    cancelled = True
                    break
            folder = Path(current)
            names = list(dirs)
            if folder != root and folder.name.casefold() in PROTECTED_DIRECTORY_NAMES:
                dirs[:] = []
                continue
            if _is_project_root(folder, names, filenames):
                dirs[:] = []
                skipped += len(filenames)
                continue
            safe = []
            for name in dirs:
                child = folder / name
                if name.casefold() in PROTECTED_DIRECTORY_NAMES or _is_reparse_or_link(child):
                    skipped += 1
                else:
                    safe.append(name)
            dirs[:] = safe
            for filename in filenames:
                if control is not None:
                    try:
                        control.checkpoint()
                    except OperationCancelled:
                        cancelled = True
                        break
                path = folder / filename
                checked += 1
                if filename.casefold() in PROTECTED_FILE_NAMES or path.suffix.casefold() in PROTECTED_FILE_EXTENSIONS or _is_reparse_or_link(path):
                    skipped += 1
                    continue
                category = category_for(path)
                if category not in selected or not extension_is_selected(path, category, filters):
                    continue
                try:
                    if not path.is_file():
                        skipped += 1
                        continue
                    text_supported = extract_text and category in TEXT_CATEGORIES
                    if not index.needs_refresh(path, require_text=text_supported):
                        # Saved text remains valid when only user topic rules have
                        # changed. Refresh the topic without reparsing the file.
                        index.refresh_classification(path, category, custom_rules)
                        indexed += 1
                        continue
                    body = read_document_text(path) if text_supported else ""
                    topic, _reason, _confidence = classify_topic(path, category, body, custom_rules)
                    index.upsert_file(path, category, body, topic, text_indexed=text_supported)
                    topic_counts[topic] = topic_counts.get(topic, 0) + 1
                    refreshed += 1
                    indexed += 1
                except (OSError, ValueError) as error:
                    skipped += 1
                if progress and checked % 100 == 0:
                    progress({"phase": "index", "root_index": len(seen_roots), "roots_total": len(seen_roots), "files_checked": checked, "files_indexed": indexed, "refreshed": refreshed, "skipped": skipped, "topics": dict(topic_counts), "current_root": str(root)})
            if cancelled:
                break
        if progress:
            progress(f"Finished indexing {root}.")
        if cancelled:
            break
    index.db.commit()
    total = index.count()
    index.close()
    return {"checked": checked, "indexed": indexed, "refreshed": refreshed, "skipped": skipped, "total": total, "cancelled": cancelled, "topics": topic_counts}
