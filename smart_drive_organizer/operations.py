from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .models import ScanPlan
from .operation_control import OperationCancelled, OperationControl

HISTORY_FOLDER = ".smart_drive_organizer_history"
CHUNK_SIZE = 1024 * 1024


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json_atomic(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".journal-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    index = 1
    while True:
        candidate = path.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _reserve_destination(path: Path) -> None:
    """Create an exclusive placeholder so concurrent/existing files are never overwritten."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(str(path), flags, 0o600)
    os.close(fd)


def _copy_verified(source: Path, destination: Path, control: Optional[OperationControl] = None) -> str:
    """Copy through a same-directory temporary file and verify hashes before publishing."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".sdo-stage-", suffix=source.suffix, dir=str(destination.parent))
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        source_hash_before = _sha256(source)
        with source.open("rb") as source_handle, temp_path.open("wb") as target_handle:
            while True:
                if control is not None:
                    control.checkpoint()
                chunk = source_handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                target_handle.write(chunk)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        shutil.copystat(source, temp_path)
        staged_hash = _sha256(temp_path)
        source_hash_after = _sha256(source)
        if source_hash_before != staged_hash or source_hash_after != staged_hash:
            raise IOError("File changed during copying or checksum verification failed; source was left untouched.")

        _reserve_destination(destination)
        try:
            os.replace(temp_path, destination)
        except Exception:
            destination.unlink(missing_ok=True)  # removes only the empty placeholder created above
            raise
        return staged_hash
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _move_file(source: Path, destination: Path, allow_rename: bool = True, control: Optional[OperationControl] = None) -> Tuple[Path, str]:
    """Move safely; same-volume moves are atomic, cross-volume moves are verified first."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if allow_rename:
        destination = _unique_path(destination)
    elif destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing path: {destination}")
    source_device = source.stat().st_dev
    destination_device = destination.parent.stat().st_dev

    if source_device == destination_device:
        _reserve_destination(destination)
        try:
            os.replace(source, destination)
        except Exception:
            destination.unlink(missing_ok=True)  # only the empty placeholder created above
            raise
        return destination, "same-volume rename"

    digest = _copy_verified(source, destination, control)
    try:
        source.unlink()
    except OSError as error:
        return destination, f"verified copy created, but original could not be moved: {error}"
    return destination, f"cross-volume copy verified ({digest[:12]}), then source relocated"


def run_plan(
    plan: ScanPlan,
    mode: str,
    progress: Optional[Callable[[str], None]] = None,
    origin: str = "manual",
    control: Optional[OperationControl] = None,
) -> Dict:
    """Apply a previewed plan. mode must be 'copy' or 'move'."""
    mode = mode.lower().strip()
    if mode not in {"copy", "move"}:
        raise ValueError("Mode must be 'copy' or 'move'.")
    if not plan.files:
        raise ValueError("There are no files in the current plan.")

    output_root = plan.output_root.expanduser().resolve()
    source_roots = plan.source_roots or [plan.source_root]
    for source_root in source_roots:
        source = source_root.expanduser().resolve()
        if source == output_root or output_root in source.parents:
            raise ValueError(
                f"Safety check failed: destination {output_root} is the same as or above scanned source {source}. "
                "Choose a destination below the source root or at another location."
            )

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    history_dir = output_root / HISTORY_FOLDER
    journal_path = history_dir / f"run_{run_id}.json"
    journal: Dict = {
        "app": "Smart Drive Organizer",
        "version": "0.7.0",
        "run_id": run_id,
        "mode": mode,
        "origin": origin,
        "source_root": str(plan.source_root),
        "source_roots": [str(item) for item in source_roots],
        "output_root": str(output_root),
        "started_at": _timestamp(),
        "finished_at": None,
        "status": "running",
        "actions": [],
    }
    for item in plan.files:
        journal["actions"].append({
            "source": str(item.source),
            "destination": str(item.destination),
            "category": item.category,
            "topic": item.topic,
            "reason": item.reason,
            "status": "pending",
            "error": None,
        })
    _write_json_atomic(journal_path, journal)

    succeeded = 0
    failed = 0
    cancelled = False
    for index, item in enumerate(plan.files, start=1):
        action = journal["actions"][index - 1]
        try:
            if control is not None:
                control.checkpoint()
            if not item.source.exists():
                raise FileNotFoundError("The source file no longer exists. The preview may be out of date.")
            target = _unique_path(item.destination)
            action["destination"] = str(target)
            action["status"] = "in_progress"
            journal["updated_at"] = _timestamp()
            _write_json_atomic(journal_path, journal)
            if mode == "copy":
                digest = _copy_verified(item.source, target, control)
                action["sha256"] = digest
                action["status"] = "copied"
            else:
                target, detail = _move_file(item.source, target, allow_rename=False, control=control)
                action["detail"] = detail
                action["status"] = "moved" if not item.source.exists() else "copied_source_kept"
                if action["status"] == "copied_source_kept":
                    action["error"] = detail
            succeeded += 1
        except OperationCancelled as error:
            action["status"] = "cancelled"
            action["error"] = str(error)
            cancelled = True
        except Exception as error:  # continue processing remaining files, preserving a per-file audit trail
            action["status"] = "failed"
            action["error"] = str(error)
            failed += 1
        action["finished_at"] = _timestamp()
        journal["updated_at"] = _timestamp()
        _write_json_atomic(journal_path, journal)
        if progress:
            progress({"phase": "apply", "processed": index, "total": len(plan.files), "current_file": item.source.name, "status": action["status"]})
        if cancelled:
            break

    journal["finished_at"] = _timestamp()
    journal["status"] = "cancelled" if cancelled else ("completed" if failed == 0 else ("partial" if succeeded else "failed"))
    source_kept = sum(1 for action in journal["actions"] if action.get("status") == "copied_source_kept")
    journal["summary"] = {"total": len(plan.files), "succeeded": succeeded, "failed": failed, "source_kept": source_kept, "cancelled": cancelled}
    _write_json_atomic(journal_path, journal)
    return {"journal_path": journal_path, "journal": journal, "succeeded": succeeded, "failed": failed, "source_kept": source_kept, "cancelled": cancelled}


def latest_movable_journal(output_root: Path, origin: Optional[str] = None) -> Optional[Path]:
    history_dir = output_root / HISTORY_FOLDER
    if not history_dir.is_dir():
        return None
    candidates = []
    for path in history_dir.glob("run_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("mode") == "move" and (origin is None or data.get("origin", "manual") == origin) and data.get("status") in {"running", "completed", "partial", "failed", "undo_partial"}:
                if any(action.get("status") in {"moved", "in_progress"} for action in data.get("actions", [])):
                    candidates.append(path)
        except (OSError, json.JSONDecodeError):
            continue
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def undo_move_journal(journal_path: Path, progress: Optional[Callable[[str], None]] = None) -> Dict:
    """Restore moved files to their original paths; never overwrites an existing original."""
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    if journal.get("mode") != "move":
        raise ValueError("Only move runs can be undone without deleting copied files.")
    restored = 0
    skipped = 0
    errors: List[str] = []

    for action in reversed(journal.get("actions", [])):
        state = action.get("status")
        if state not in {"moved", "in_progress"}:
            continue
        source_now = Path(action["destination"])
        original = Path(action["source"])
        try:
            organized_exists = source_now.exists()
            original_exists = original.exists()
            if state == "in_progress" and organized_exists and original_exists:
                # Likely interrupted after a cross-volume copy was published but before source relocation.
                action["status"] = "recovery_copy_left"
                action["undo_error"] = "Both source and destination exist; neither was removed or overwritten."
                skipped += 1
                errors.append(f"Both copies exist; left both untouched: {original} | {source_now}")
                _write_json_atomic(journal_path, journal)
                continue
            if state == "in_progress" and original_exists and not organized_exists:
                action["status"] = "not_applied"
                skipped += 1
                errors.append(f"Move had not been applied; original remains in place: {original}")
                _write_json_atomic(journal_path, journal)
                continue
            if not organized_exists:
                skipped += 1
                errors.append(f"Missing organized file; not restored: {source_now}")
                continue
            if original_exists:
                skipped += 1
                errors.append(f"Original path is occupied; left organized file in place: {original}")
                continue
            original.parent.mkdir(parents=True, exist_ok=True)
            restored_path, detail = _move_file(source_now, original, allow_rename=False)
            if restored_path != original:
                raise IOError("The file could not be restored to its exact original path.")
            if source_now.exists():
                # A verified restore copy exists, but the organized copy could not be relocated.
                action["status"] = "restore_copy_created_source_kept"
                action["undo_error"] = detail
                skipped += 1
                errors.append(f"Restored a copy but could not relocate the organized copy: {source_now}")
            else:
                action["status"] = "undone"
                action["undone_at"] = _timestamp()
                restored += 1
        except Exception as error:
            skipped += 1
            errors.append(f"Could not restore {source_now}: {error}")
        if progress:
            progress(f"Restored {restored:,} file(s); skipped {skipped:,}.")
        _write_json_atomic(journal_path, journal)

    journal["undo_finished_at"] = _timestamp()
    journal["undo_summary"] = {"restored": restored, "skipped": skipped, "errors": errors}
    journal["status"] = "undone" if skipped == 0 else "undo_partial"
    _write_json_atomic(journal_path, journal)
    return {"restored": restored, "skipped": skipped, "errors": errors}
