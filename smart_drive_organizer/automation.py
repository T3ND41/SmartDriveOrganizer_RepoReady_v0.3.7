from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .classifier import category_for, classify_selected_topic, classify_topic, extension_bucket, load_custom_rules, load_topic_rules, normalize_topic_rules, save_topic_rules, safe_folder_name, selected_topic_destination, selected_topic_destinations
from .content_reader import read_document_text
from .file_types import extension_is_selected, load_extension_filters, normalize_extension_filters
from .models import PlannedFile, ScanPlan
from .operations import _copy_verified, _unique_path, run_plan
from .scanner import (
    PROTECTED_DIRECTORY_NAMES,
    PROTECTED_FILE_EXTENSIONS,
    PROTECTED_FILE_NAMES,
    _is_project_root,
    _is_reparse_or_link,
)

APP_NAME = "SmartDriveOrganizer"
DEFAULT_POLL_SECONDS = 10
DEFAULT_STABLE_OBSERVATIONS = 3
TEMP_SUFFIXES = {".crdownload", ".part", ".tmp", ".download", ".partial", ".opdownload"}


def app_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return app_data_dir() / "automation_settings.json"


def topic_rules_path(app_dir: Optional[Path] = None, published_file: Optional[Path] = None) -> Path:
    """Return the permanent per-user rules file and merge shared repository presets.

    User rules live in the OS application-data directory. When a shared preset file
    is shipped in the repository, new groups/keywords are merged into the local
    rules without overwriting the user's local destinations or existing choices.
    """
    directory = app_dir or app_data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "topic_rules.json"
    published = published_file or (Path(__file__).resolve().parent.parent / "config" / "published_topic_rules.json")

    def read_published() -> list[dict[str, Any]]:
        try:
            data = json.loads(published.read_text(encoding="utf-8"))
            values = data.get("rules", []) if isinstance(data, dict) else data
            return values if isinstance(values, list) else []
        except (OSError, json.JSONDecodeError, TypeError):
            return []

    shared = normalize_topic_rules(read_published())
    if not target.exists():
        save_topic_rules(target, shared)
        return target

    if shared:
        local = load_topic_rules(target)
        by_name = {rule["name"].casefold(): rule for rule in local}
        changed = False
        for shared_rule in shared:
            key = shared_rule["name"].casefold()
            current = by_name.get(key)
            if current is None:
                local.append(shared_rule)
                by_name[key] = shared_rule
                changed = True
                continue
            merged_keywords = list(dict.fromkeys(current.get("keywords", []) + shared_rule.get("keywords", [])))
            if merged_keywords != current.get("keywords", []):
                current["keywords"] = merged_keywords
                changed = True
            # Preserve local destination and scope; only fill an empty destination.
            if not current.get("destination") and shared_rule.get("destination"):
                current["destination"] = shared_rule["destination"]
                changed = True
        if changed:
            save_topic_rules(target, local)
    return target


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve()))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _default_downloads() -> list[str]:
    candidate = Path.home() / "Downloads"
    return [str(candidate)] if candidate.is_dir() else []


@dataclass
class AutomationConfig:
    enabled: bool = False
    monitor_folders: list[str] = field(default_factory=_default_downloads)
    output_folder: str = str(Path.home() / "Documents" / "Organized Files")
    categories: list[str] = field(default_factory=lambda: [
        "Documents", "Images", "Videos", "Audio", "Archives", "Code",
        "Applications", "Fonts", "3D Models", "Others",
    ])
    mode: str = "copy"
    read_document_text: bool = True
    start_with_windows: bool = False
    poll_interval_seconds: int = DEFAULT_POLL_SECONDS
    stable_observations: int = DEFAULT_STABLE_OBSERVATIONS
    topic_filter_enabled: bool = False
    selected_topics: list[str] = field(default_factory=list)
    extension_filters: dict[str, list[str]] = field(default_factory=load_extension_filters)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutomationConfig":
        defaults = cls()
        categories = data.get("categories", defaults.categories)
        folders = data.get("monitor_folders", defaults.monitor_folders)
        mode = str(data.get("mode", defaults.mode)).lower()
        return cls(
            enabled=bool(data.get("enabled", defaults.enabled)),
            monitor_folders=[str(item) for item in folders if str(item).strip()] if isinstance(folders, list) else defaults.monitor_folders,
            output_folder=str(data.get("output_folder", defaults.output_folder)),
            categories=[str(item) for item in categories] if isinstance(categories, list) else defaults.categories,
            mode=mode if mode in {"copy", "move"} else "copy",
            read_document_text=bool(data.get("read_document_text", defaults.read_document_text)),
            start_with_windows=bool(data.get("start_with_windows", defaults.start_with_windows)),
            poll_interval_seconds=max(3, min(300, int(data.get("poll_interval_seconds", defaults.poll_interval_seconds)))),
            stable_observations=max(2, min(12, int(data.get("stable_observations", defaults.stable_observations)))),
            topic_filter_enabled=bool(data.get("topic_filter_enabled", defaults.topic_filter_enabled)),
            selected_topics=[str(item) for item in data.get("selected_topics", defaults.selected_topics) if str(item).strip()] if isinstance(data.get("selected_topics", defaults.selected_topics), list) else defaults.selected_topics,
            extension_filters=normalize_extension_filters(data.get("extension_filters", defaults.extension_filters)),
        )


def load_settings(path: Optional[Path] = None) -> AutomationConfig:
    target = path or settings_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return AutomationConfig.from_dict(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return AutomationConfig()


def save_settings(config: AutomationConfig, path: Optional[Path] = None) -> Path:
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(asdict(config), handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, target)
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise
    return target


def validate_config(config: AutomationConfig, allow_missing_roots: bool = False) -> list[Path]:
    if not config.enabled:
        raise ValueError("Automatic monitoring is not enabled. Enable it in Automation Settings first.")
    if not config.monitor_folders:
        raise ValueError("Add at least one folder to monitor, such as Downloads.")
    if not config.output_folder.strip():
        raise ValueError("Choose an output folder for organized files.")
    if not config.categories:
        raise ValueError("Select at least one file category.")
    if config.topic_filter_enabled and not config.selected_topics:
        raise ValueError("Select at least one topic group when selective organization is enabled.")
    output = Path(config.output_folder).expanduser().resolve()
    if output.exists() and not output.is_dir():
        raise ValueError("The output destination exists as a file. Choose a folder instead.")
    if output == output.parent or any(part.casefold() in PROTECTED_DIRECTORY_NAMES for part in output.parts):
        raise ValueError("Choose a named output folder outside protected Windows/system directories.")
    roots: list[Path] = []
    for value in config.monitor_folders:
        root = Path(value).expanduser().resolve()
        if not root.exists():
            if not allow_missing_roots:
                raise ValueError(f"The monitored folder does not exist or is unavailable: {root}")
        elif not root.is_dir():
            raise ValueError(f"The monitored location is not a folder: {root}")
        if root.name.casefold() in PROTECTED_DIRECTORY_NAMES:
            raise ValueError(f"This is a protected folder and cannot be monitored: {root}")
        if root.exists():
            if _is_reparse_or_link(root):
                raise ValueError(f"This is a link and cannot be monitored: {root}")
            try:
                root_names = [item.name for item in root.iterdir() if item.is_dir()]
                root_files = [item.name for item in root.iterdir() if item.is_file()]
                if _is_project_root(root, root_names, root_files):
                    raise ValueError(f"This appears to be a software project root. Monitor a folder outside the project instead: {root}")
            except PermissionError as error:
                raise ValueError(f"Windows denied access to the monitored folder: {root}") from error
        if root == output or output in root.parents:
            raise ValueError(f"The output folder cannot be the same as or an ancestor of a monitored folder: {root}")
        roots.append(root)
    # Collapse nested roots to ensure a file is only indexed once.
    roots = sorted({Path(_norm(item)) for item in roots}, key=lambda item: (len(item.parts), _norm(item)))
    normalized: list[Path] = []
    for candidate in roots:
        if any(candidate == parent or parent in candidate.parents for parent in normalized):
            continue
        normalized.append(candidate)
    return normalized


def _iter_candidate_files(
    root: Path,
    output: Path,
    prune_output: bool,
    stop_requested: Callable[[], bool],
    excluded_paths: Optional[list[Path]] = None,
):
    excluded = [path.expanduser().resolve() for path in (excluded_paths or [])]
    def is_excluded(path: Path) -> bool:
        return any(path.resolve() == target or target in path.resolve().parents for target in excluded)
    def on_error(_error: OSError) -> None:
        return

    for current, dirs, filenames in os.walk(root, topdown=True, followlinks=False, onerror=on_error):
        if stop_requested():
            return
        current_path = Path(current)
        if prune_output and _is_relative_to(current_path, output):
            dirs[:] = []
            continue
        if is_excluded(current_path):
            dirs[:] = []
            continue
        if current_path != root and current_path.name.casefold() in PROTECTED_DIRECTORY_NAMES:
            dirs[:] = []
            continue
        if current_path != root and _is_project_root(current_path, dirs, filenames):
            dirs[:] = []
            continue
        safe_dirs: list[str] = []
        for name in dirs:
            child = current_path / name
            if name.casefold() in PROTECTED_DIRECTORY_NAMES or _is_reparse_or_link(child):
                continue
            if prune_output and _is_relative_to(child, output):
                continue
            if is_excluded(child):
                continue
            safe_dirs.append(name)
        dirs[:] = safe_dirs
        for filename in filenames:
            if stop_requested():
                return
            path = current_path / filename
            if filename.casefold() in PROTECTED_FILE_NAMES:
                continue
            if path.suffix.casefold() in PROTECTED_FILE_EXTENSIONS or path.suffix.casefold() in TEMP_SUFFIXES:
                continue
            if filename.startswith("~$") or filename.startswith(".~"):
                continue
            if _is_reparse_or_link(path):
                continue
            try:
                if path.is_file():
                    yield path
            except OSError:
                continue


def _exclusive_read_check(path: Path) -> bool:
    """On Windows, reject files with an active writer handle; elsewhere use stat stability."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create_file.restype = wintypes.HANDLE
        # Share-read only: an existing handle opened for writing must also be
        # permitted by this share mode, so the check fails while a writer is active.
        handle = create_file(str(path), 0x80000000, 0x00000001, None, 3, 0x80, None)  # GENERIC_READ, FILE_SHARE_READ
        invalid = wintypes.HANDLE(-1).value
        if handle == invalid:
            return False
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        close_handle(handle)
        return True
    except Exception:
        return False


def _append_activity(app_dir: Path, record: dict[str, Any]) -> None:
    target = app_dir / "automation_activity.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()


def _organize_file(source: Path, config: AutomationConfig, roots: list[Path], rules: list[dict[str, Any]], topic_rules: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    source = source.resolve()
    if not source.is_file() or _is_reparse_or_link(source):
        return {"status": "skipped", "reason": "The file is missing, not a regular file, or is a link."}
    if not any(_is_relative_to(source, root) for root in roots):
        return {"status": "skipped", "reason": "The file is outside the monitored folders."}

    output = Path(config.output_folder).expanduser().resolve()
    prune_output = any(_is_relative_to(output, root) for root in roots)
    if prune_output and _is_relative_to(source, output):
        return {"status": "skipped", "reason": "The file is already inside the organizer output folder."}
    category = category_for(source)
    if category not in config.categories:
        return {"status": "ignored", "reason": f"File category '{category}' is not enabled; original file left untouched."}
    if not extension_is_selected(source, category, config.extension_filters):
        return {"status": "ignored", "reason": f"File format '{source.suffix or '(no extension)'}' is not selected for {category}; original file left untouched."}
    content = ""
    try:
        if config.read_document_text and category == "Documents" and source.stat().st_size <= 20 * 1024 * 1024:
            content = read_document_text(source)
    except OSError:
        content = ""

    if config.topic_filter_enabled:
        selected_match = classify_selected_topic(source, category, content, config.selected_topics, rules, topic_rules)
        if selected_match is None:
            return {"status": "ignored", "reason": "File did not match any selected topic; original file left untouched."}
        topic, reason, confidence = selected_match
    else:
        topic, reason, confidence = classify_topic(source, category, content, rules)
    topic = safe_folder_name(topic)
    extension = extension_bucket(source)
    custom_destination = selected_topic_destination(topic, topic_rules) if config.topic_filter_enabled else None
    if custom_destination is not None:
        if custom_destination.exists() and not custom_destination.is_dir():
            return {"status": "failed", "reason": f"Custom destination exists as a file: {custom_destination}"}
        if any(custom_destination == root or custom_destination in root.parents for root in roots):
            return {"status": "failed", "reason": f"Custom destination cannot be the same as or an ancestor of a monitored folder: {custom_destination}"}
        if any(part.casefold() in PROTECTED_DIRECTORY_NAMES for part in custom_destination.parts):
            return {"status": "failed", "reason": f"Custom destination is inside a protected folder: {custom_destination}"}
        base_destination = custom_destination / source.name
    else:
        base_destination = output / safe_folder_name(category) / topic / safe_folder_name(extension) / source.name

    if config.mode == "move":
        source_root = next(root for root in roots if _is_relative_to(source, root))
        item = PlannedFile(
            source=source,
            category=category,
            topic=topic,
            extension_folder=extension,
            destination=base_destination,
            reason=reason,
            confidence=confidence,
            size_bytes=source.stat().st_size,
        )
        plan = ScanPlan(
            source_root=source_root,
            output_root=output,
            selected_categories=[category],
            files=[item],
            source_roots=[source_root],
        )
        moved = run_plan(plan, "move", origin="automatic")
        action = moved["journal"]["actions"][0]
        status = str(action.get("status", "failed"))
        return {
            "status": status,
            "source": str(source),
            "destination": str(action.get("destination", base_destination)),
            "category": category,
            "topic": topic,
            "extension": extension,
            "reason": reason,
            "confidence": confidence,
            "detail": action.get("detail", action.get("error", "")),
            "journal_path": str(moved["journal_path"]),
            "mode": config.mode,
        }

    last_error: Optional[Exception] = None
    for _ in range(100):
        destination = _unique_path(base_destination)
        try:
            digest = _copy_verified(source, destination)
            return {
                "status": "copied",
                "source": str(source),
                "destination": str(destination),
                "category": category,
                "topic": topic,
                "extension": extension,
                "reason": reason,
                "confidence": confidence,
                "detail": f"SHA-256 verified: {digest}",
                "mode": config.mode,
            }
        except FileExistsError as error:
            last_error = error
            continue
    raise FileExistsError(f"Could not reserve a unique destination for {source.name}: {last_error}")


class AutomationEngine:
    """Polling-based watch-folder engine with a persistent SQLite file-state index.

    Existing files are baselined on the first run of each monitored folder. New files,
    and files that disappear then reappear at a path, are considered for organization.
    """

    def __init__(self, config: AutomationConfig, app_dir: Optional[Path] = None, stop_requested: Optional[Callable[[], bool]] = None):
        self.config = config
        self.app_dir = app_dir or app_data_dir()
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.app_dir / "automation_state.sqlite3"
        self.activity_path = self.app_dir / "automation_activity.jsonl"
        self.roots = validate_config(config, allow_missing_roots=True)
        self.output = Path(config.output_folder).expanduser().resolve()
        self.prune_output = any(_is_relative_to(self.output, root) for root in self.roots)
        self.topic_rules = load_topic_rules(topic_rules_path(self.app_dir))
        self.route_destinations = selected_topic_destinations(config.selected_topics, self.topic_rules) if config.topic_filter_enabled else []
        for route_destination in self.route_destinations:
            if route_destination.exists() and not route_destination.is_dir():
                raise ValueError(f"A custom topic destination exists as a file: {route_destination}")
            if any(route_destination == root or route_destination in root.parents for root in self.roots):
                raise ValueError(f"A custom topic destination cannot be the same as or an ancestor of a monitored folder: {route_destination}")
            if any(part.casefold() in PROTECTED_DIRECTORY_NAMES for part in route_destination.parts):
                raise ValueError(f"A custom topic destination is inside a protected folder: {route_destination}")
        self.stop_requested = stop_requested or (lambda: False)
        self.connection = sqlite3.connect(self.db_path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self._create_tables()
        self.last_scan_count = 0
        self.last_processed = 0
        self.last_message = "Starting baseline scan."

    def _create_tables(self) -> None:
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS roots (
                path TEXT PRIMARY KEY,
                generation INTEGER NOT NULL DEFAULT 0,
                initialized INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                root TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                generation INTEGER NOT NULL,
                stable_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                detail TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_files_root_status ON files(root, status);
        """)
        self.connection.commit()

    def close(self) -> None:
        try:
            self.connection.close()
        except Exception:
            pass

    def _refresh_topic_rules(self) -> None:
        """Refresh routing rules so saved edits take effect without restarting the monitor."""
        latest_rules = load_topic_rules(topic_rules_path(self.app_dir))
        latest_destinations = selected_topic_destinations(self.config.selected_topics, latest_rules) if self.config.topic_filter_enabled else []
        for route_destination in latest_destinations:
            if route_destination.exists() and not route_destination.is_dir():
                raise ValueError(f"A custom topic destination exists as a file: {route_destination}")
            if any(route_destination == root or route_destination in root.parents for root in self.roots):
                raise ValueError(f"A custom topic destination cannot be the same as or an ancestor of a monitored folder: {route_destination}")
            if any(part.casefold() in PROTECTED_DIRECTORY_NAMES for part in route_destination.parts):
                raise ValueError(f"A custom topic destination is inside a protected folder: {route_destination}")
        self.topic_rules = latest_rules
        self.route_destinations = latest_destinations

    def _baseline_root(self, root: Path, root_key: str) -> int:
        self.last_message = f"Creating initial baseline for {root}. Existing files will not be moved automatically."
        count = 0
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                "INSERT OR REPLACE INTO roots(path, generation, initialized) VALUES (?, 1, 1)",
                (root_key,),
            )
            for path in _iter_candidate_files(root, self.output, self.prune_output, self.stop_requested, self.route_destinations):
                if self.stop_requested():
                    self.connection.rollback()
                    self.last_message = f"Baseline interrupted for {root}; it will restart safely next time."
                    return 0
                try:
                    info = path.stat()
                    self.connection.execute(
                        "INSERT OR REPLACE INTO files(path, root, size, mtime_ns, generation, stable_count, status, detail, updated_at) VALUES (?, ?, ?, ?, 1, 0, 'baseline', 'Present before monitoring baseline', ?)",
                        (_norm(path), root_key, info.st_size, info.st_mtime_ns, _now()),
                    )
                    count += 1
                except OSError:
                    continue
            if self.stop_requested():
                self.connection.rollback()
                self.last_message = f"Baseline interrupted for {root}; it will restart safely next time."
                return 0
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        _append_activity(self.app_dir, {"time": _now(), "event": "baseline_created", "root": str(root), "files_indexed": count})
        return count

    def _scan_existing_root(self, root: Path, root_key: str, previous_generation: int) -> list[Path]:
        generation = previous_generation + 1
        stable_candidates: list[Path] = []
        self.last_scan_count = 0
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            for path in _iter_candidate_files(root, self.output, self.prune_output, self.stop_requested, self.route_destinations):
                if self.stop_requested():
                    break
                try:
                    info = path.stat()
                    key = _norm(path)
                except OSError:
                    continue
                row = self.connection.execute(
                    "SELECT size, mtime_ns, generation, stable_count, status FROM files WHERE path = ?",
                    (key,),
                ).fetchone()
                self.last_scan_count += 1
                if row is None:
                    self.connection.execute(
                        "INSERT INTO files(path, root, size, mtime_ns, generation, stable_count, status, detail, updated_at) VALUES (?, ?, ?, ?, ?, 1, 'pending', NULL, ?)",
                        (key, root_key, info.st_size, info.st_mtime_ns, generation, _now()),
                    )
                    continue

                was_seen_previous_cycle = int(row["generation"]) == previous_generation
                old_signature = (int(row["size"]), int(row["mtime_ns"]))
                new_signature = (info.st_size, info.st_mtime_ns)
                status = str(row["status"])
                if not was_seen_previous_cycle:
                    # A path absent for one or more successful scans has reappeared.
                    stable_count = 1
                    status = "pending"
                elif status == "pending":
                    stable_count = int(row["stable_count"]) + 1 if old_signature == new_signature else 1
                else:
                    stable_count = int(row["stable_count"])
                    # Modifying an already-known file does not create another organized copy.
                    if old_signature != new_signature and status in {"baseline", "processed", "ignored", "failed", "known"}:
                        status = "known"
                        stable_count = 0
                self.connection.execute(
                    "UPDATE files SET root=?, size=?, mtime_ns=?, generation=?, stable_count=?, status=?, updated_at=? WHERE path=?",
                    (root_key, info.st_size, info.st_mtime_ns, generation, stable_count, status, _now(), key),
                )
                if status == "pending" and stable_count >= self.config.stable_observations:
                    stable_candidates.append(path)
            if self.stop_requested():
                self.connection.rollback()
                self.last_message = f"Scan interrupted for {root}; no partial scan state was committed."
                return []
            self.connection.execute("UPDATE roots SET generation=? WHERE path=?", (generation, root_key))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return stable_candidates

    def _record_result(self, source: Path, status: str, detail: str) -> None:
        self.connection.execute(
            "UPDATE files SET status=?, detail=?, updated_at=? WHERE path=?",
            (status, detail[:2000], _now(), _norm(source)),
        )
        self.connection.commit()
        try:
            _append_activity(self.app_dir, {"time": _now(), "event": "file_organization", "status": status, "source": str(source), "detail": detail})
        except OSError as error:
            # A log-disk error must not misreport a file operation that already succeeded.
            self.last_message = f"File action completed, but the activity log could not be written: {error}"

    def scan_once(self) -> dict[str, int]:
        indexed = 0
        processed = 0
        warnings = 0
        try:
            self._refresh_topic_rules()
        except ValueError as error:
            self.last_message = f"Custom topic routing settings are invalid: {error}"
            return {"indexed": 0, "processed": 0, "warnings": 1}
        rules_path = self.app_dir / "keyword_rules.json"
        rules = load_custom_rules(rules_path)
        topic_rules = self.topic_rules
        for root in self.roots:
            if self.stop_requested():
                break
            if not root.exists() or not root.is_dir():
                warnings += 1
                self.last_message = f"Monitored folder is unavailable: {root}"
                continue
            root_key = _norm(root)
            row = self.connection.execute("SELECT generation, initialized FROM roots WHERE path=?", (root_key,)).fetchone()
            if row is None or not int(row["initialized"]):
                indexed += self._baseline_root(root, root_key)
                continue
            candidates = self._scan_existing_root(root, root_key, int(row["generation"]))
            indexed += self.last_scan_count
            output_anchor = Path(self.output.anchor) if self.output.anchor else self.output
            if candidates and not output_anchor.exists():
                warnings += 1
                self.last_message = f"Destination drive is unavailable ({output_anchor}); new files remain queued in their source folders."
                continue
            for source in candidates:
                if self.stop_requested():
                    break
                try:
                    # A final stat/lock check guards against incomplete downloads.
                    source.stat()  # fail cleanly if the file vanished between scan and action
                    if not _exclusive_read_check(source):
                        self.connection.execute(
                            "UPDATE files SET stable_count=0, generation=(SELECT generation FROM roots WHERE path=?)-1 WHERE path=?",
                            (root_key, _norm(source)),
                        )
                        self.connection.commit()
                        continue
                    result = _organize_file(source, self.config, self.roots, rules, topic_rules)
                    status = str(result.get("status", "failed"))
                    self._record_result(source, status, json.dumps(result, ensure_ascii=False))
                    processed += 1 if status in {"copied", "moved", "copied_source_kept"} else 0
                    if status == "failed":
                        warnings += 1
                except Exception as error:
                    self._record_result(source, "failed", str(error))
                    warnings += 1
            self.last_processed = processed
        self.last_message = f"Checked {indexed:,} file(s); organized {processed:,} new file(s); {warnings:,} warning(s)."
        return {"indexed": indexed, "processed": processed, "warnings": warnings}


def service_status_path() -> Path:
    return app_data_dir() / "automation_status.json"


def service_lock_path() -> Path:
    return app_data_dir() / "automation_service.lock"


def service_log_path() -> Path:
    return app_data_dir() / "automation_service.log"


def _write_status(data: dict[str, Any]) -> None:
    target = service_status_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, target)


def read_service_status() -> dict[str, Any]:
    try:
        return json.loads(service_status_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def is_service_running() -> bool:
    lock = service_lock_path()
    if not lock.exists():
        return False
    try:
        pid = int(lock.read_text(encoding="utf-8").strip())
        if pid <= 0:
            return False
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (OSError, TypeError, ValueError):
        return False


def request_service_stop() -> None:
    marker = app_data_dir() / "automation_stop.request"
    marker.write_text(_now(), encoding="utf-8")


def mark_undo_restored_sources(
    journal_path: Path,
    app_dir: Optional[Path] = None,
    config: Optional[AutomationConfig] = None,
) -> int:
    """Update the watch index after a Move journal restores originals to monitored paths."""
    directory = app_dir or app_data_dir()
    database = directory / "automation_state.sqlite3"
    if not database.exists():
        return 0
    try:
        journal = json.loads(Path(journal_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    active_config = config or load_settings()
    roots = [Path(item).expanduser().resolve() for item in active_config.monitor_folders]
    connection = sqlite3.connect(database, timeout=30)
    try:
        restored = 0
        for action in journal.get("actions", []):
            if action.get("status") != "undone":
                continue
            source = Path(action.get("source", "")).expanduser()
            try:
                source = source.resolve()
                if not source.is_file():
                    continue
                root = next((candidate for candidate in roots if _is_relative_to(source, candidate)), None)
                if root is None:
                    continue
                root_key = _norm(root)
                root_row = connection.execute("SELECT generation FROM roots WHERE path=?", (root_key,)).fetchone()
                if root_row is None:
                    continue
                info = source.stat()
                connection.execute(
                    "INSERT INTO files(path, root, size, mtime_ns, generation, stable_count, status, detail, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 0, 'baseline', 'Restored by undo; do not automatically move again', ?) "
                    "ON CONFLICT(path) DO UPDATE SET root=excluded.root, size=excluded.size, mtime_ns=excluded.mtime_ns, "
                    "generation=excluded.generation, stable_count=0, status='baseline', detail=excluded.detail, updated_at=excluded.updated_at",
                    (_norm(source), root_key, info.st_size, info.st_mtime_ns, int(root_row[0]), _now()),
                )
                restored += 1
            except OSError:
                continue
        connection.commit()
        if restored:
            try:
                _append_activity(directory, {"time": _now(), "event": "undo_restored", "journal": str(journal_path), "files": restored})
            except OSError:
                pass
        return restored
    finally:
        connection.close()


def _acquire_lock() -> Path:
    lock = service_lock_path()
    if lock.exists():
        try:
            old_pid = int(lock.read_text(encoding="utf-8").strip())
            os.kill(old_pid, 0)
            raise RuntimeError(f"A background organizer process already appears to be running (PID {old_pid}).")
        except PermissionError:
            raise RuntimeError("A background organizer process is already running.")
        except (ProcessLookupError, ValueError):
            lock.unlink(missing_ok=True)
        except OSError:
            # Windows may report a missing PID as a generic OSError/WinError.
            lock.unlink(missing_ok=True)
    fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    return lock


def run_background_service() -> int:
    config = load_settings()
    stop_file = app_data_dir() / "automation_stop.request"
    stop_file.unlink(missing_ok=True)
    lock = _acquire_lock()
    started = _now()
    status: dict[str, Any] = {
        "running": True, "pid": os.getpid(), "started_at": started,
        "heartbeat": started, "last_message": "Starting automatic monitor.",
        "files_organized": 0, "warnings": 0,
    }
    engine: Optional[AutomationEngine] = None

    def stop_requested() -> bool:
        return stop_file.exists()

    try:
        engine = AutomationEngine(config, stop_requested=stop_requested)
        _write_status(status)
        while not stop_requested():
            try:
                result = engine.scan_once()
                status.update({
                    "heartbeat": _now(),
                    "last_message": engine.last_message,
                    "files_organized": int(status.get("files_organized", 0)) + result["processed"],
                    "warnings": int(status.get("warnings", 0)) + result["warnings"],
                })
            except Exception as error:
                status["last_message"] = f"Monitor cycle error: {error}"
                status["warnings"] = int(status.get("warnings", 0)) + 1
            _write_status(status)
            for _ in range(config.poll_interval_seconds):
                if stop_requested():
                    break
                time.sleep(1)
    except Exception as error:
        status["last_message"] = f"Monitor stopped: {error}"
        status["warnings"] = int(status.get("warnings", 0)) + 1
        return_code = 1
    else:
        return_code = 0
    finally:
        if engine:
            engine.close()
        status.update({"running": False, "stopped_at": _now(), "heartbeat": _now()})
        try:
            _write_status(status)
        finally:
            lock.unlink(missing_ok=True)
            stop_file.unlink(missing_ok=True)
    return return_code


def _background_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--background"]
    project_root = Path(__file__).resolve().parent.parent
    script = project_root / "run.py"
    executable = Path(sys.executable)
    if os.name == "nt":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            executable = pythonw
    return [str(executable), str(script), "--background"]


def start_background_monitor() -> int:
    config = load_settings()
    validate_config(config, allow_missing_roots=True)
    if is_service_running():
        return int(read_service_status().get("pid", 0))
    (app_data_dir() / "automation_stop.request").unlink(missing_ok=True)
    command = _background_command()
    log_handle = service_log_path().open("a", encoding="utf-8")
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "cwd": str(Path(__file__).resolve().parent.parent),
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    else:
        kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen(command, **kwargs)
    finally:
        log_handle.close()
    return process.pid


def stop_background_monitor() -> None:
    if is_service_running():
        request_service_stop()


def set_windows_startup(enabled: bool) -> None:
    if os.name != "nt":
        if enabled:
            raise RuntimeError("Automatic Windows sign-in startup is available only on Windows.")
        return
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    command = subprocess.list2cmdline(_background_command())
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        if enabled:
            winreg.SetValueEx(key, "SmartDriveOrganizer", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "SmartDriveOrganizer")
            except FileNotFoundError:
                pass
