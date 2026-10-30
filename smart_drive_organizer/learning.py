from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .classifier import normalize_text


def memory_path(directory: Optional[Path] = None) -> Path:
    if directory is None:
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        directory = base / "SmartDriveOrganizer"
    return directory / "learning_memory.json"


def empty_memory() -> dict[str, Any]:
    return {"version": 1, "approved_groups": [], "rejected_groups": [], "filing_corrections": []}


def load_memory(path: Optional[Path] = None) -> dict[str, Any]:
    target = path or memory_path()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return empty_memory()
        result = empty_memory()
        for key in ("approved_groups", "rejected_groups", "filing_corrections"):
            items = value.get(key, [])
            if isinstance(items, list):
                result[key] = [item for item in items if isinstance(item, dict)]
        return result
    except (OSError, json.JSONDecodeError, TypeError):
        return empty_memory()


def save_memory(value: dict[str, Any], path: Optional[Path] = None) -> Path:
    target = path or memory_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".learning-", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except Exception:
        try: os.unlink(temp_name)
        except OSError: pass
        raise
    return target


def _key(category: str, phrase: str) -> str:
    return category.casefold().strip() + "|" + normalize_text(phrase)


def record_discovery_decisions(approved: list[dict], rejected: list[dict],
                               path: Optional[Path] = None) -> dict[str, int]:
    memory = load_memory(path)
    now = datetime.now(timezone.utc).isoformat()
    for group in approved:
        category = str(group.get("category", "Any"))
        phrase = str(group.get("phrase", "")).strip()
        if not phrase: continue
        key = _key(category, phrase)
        memory["rejected_groups"] = [
            item for item in memory["rejected_groups"]
            if _key(str(item.get("category", "Any")), str(item.get("phrase", ""))) != key
        ]
        old = next((item for item in memory["approved_groups"]
                    if _key(str(item.get("category", "Any")), str(item.get("phrase", ""))) == key), None)
        record = {"category": category, "phrase": phrase, "name": str(group.get("name", phrase)), "updated_at": now}
        if old: old.update(record)
        else: memory["approved_groups"].append(record)
    for group in rejected:
        category = str(group.get("category", "Any"))
        phrase = str(group.get("phrase", "")).strip()
        if not phrase: continue
        key = _key(category, phrase)
        if any(_key(str(item.get("category", "Any")), str(item.get("phrase", ""))) == key
               for item in memory["approved_groups"]):
            continue
        old = next((item for item in memory["rejected_groups"]
                    if _key(str(item.get("category", "Any")), str(item.get("phrase", ""))) == key), None)
        record = {"category": category, "phrase": phrase, "name": str(group.get("name", phrase)), "updated_at": now}
        if old: old.update(record)
        else: memory["rejected_groups"].append(record)
    save_memory(memory, path)
    return {"approved": len(approved), "rejected": len(rejected)}


def rejected_discovery_patterns(path: Optional[Path] = None) -> list[dict[str, str]]:
    memory = load_memory(path)
    return [{
        "category": str(item.get("category", "Any")),
        "phrase": str(item.get("phrase", "")),
    } for item in memory["rejected_groups"] if str(item.get("phrase", "")).strip()]


def record_filing_correction(category: str, phrase: str, topic: str,
                             source_path: str = "", destination: str = "",
                             path: Optional[Path] = None) -> Path:
    memory = load_memory(path)
    now = datetime.now(timezone.utc).isoformat()
    key = _key(category, phrase)
    old = next((item for item in memory["filing_corrections"]
                if _key(str(item.get("category", "Any")), str(item.get("phrase", ""))) == key), None)
    record = {
        "category": category, "phrase": phrase, "topic": topic,
        "source_example": source_path, "destination": destination, "updated_at": now,
    }
    if old: old.update(record)
    else: memory["filing_corrections"].append(record)
    return save_memory(memory, path)


def memory_summary(path: Optional[Path] = None) -> dict[str, int]:
    value = load_memory(path)
    return {key: len(value[key]) for key in ("approved_groups", "rejected_groups", "filing_corrections")}
