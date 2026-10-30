from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Set

from .classifier import category_for, classify_selected_topic, classify_topic, extension_bucket, selected_topic_destination
from .content_reader import read_document_text
from .discovery import discover_repeated_groups
from .file_types import extension_is_selected, normalize_extension_filters
from .models import PlannedFile, ScanPlan

PROTECTED_DIRECTORY_NAMES = {
    "$recycle.bin", "recycler", "system volume information", "windows", "program files",
    "program files (x86)", "programdata", "recovery", "perflogs", "$winreagent",
    "documents and settings", "appdata", "proc", "sys", "dev", "run", "lost+found",
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv",
    "__pycache__", ".pytest_cache", ".mypy_cache",
}
PROTECTED_FILE_NAMES = {
    "pagefile.sys", "swapfile.sys", "hiberfil.sys", "bootmgr", "bootmgr.efi",
    "ntldr", "desktop.ini", "thumbs.db", "dumpstack.log.tmp",
}
PROTECTED_FILE_EXTENSIONS = {".lnk", ".url", ".crdownload", ".part", ".tmp", ".download", ".partial"}
PROJECT_MARKERS = {
    ".git", "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
    "composer.json", "pom.xml", "build.gradle", "*.sln", "*.csproj",
}


def _is_reparse_or_link(path: Path) -> bool:
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            return True
        attrs = getattr(info, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        recall_on_open = 0x00040000
        recall_on_data_access = 0x00400000
        system_flag = 0x00000004
        return bool(attrs & (reparse_flag | recall_on_open | recall_on_data_access | system_flag))
    except OSError:
        return True


def _is_project_root(directory: Path, names: List[str], files: List[str]) -> bool:
    lower_names = {name.casefold() for name in names}
    lower_files = {name.casefold() for name in files}
    if ".git" in lower_names or any(marker in lower_files for marker in PROJECT_MARKERS if not marker.startswith("*")):
        return True
    if any(name.casefold().endswith((".sln", ".csproj")) for name in files):
        return True
    return False


def _unsafe_output_overlap(source: Path, output: Path) -> bool:
    # A destination strictly inside a selected source is safe because the scan
    # explicitly prunes that directory. The same path or an ancestor destination
    # is unsafe because it would replace/contain the source tree.
    return source == output or output in source.parents


def _selected_route_destinations(selected_topics: Optional[Iterable[str]], topic_rules: Optional[list]) -> list[Path]:
    destinations: list[Path] = []
    seen: set[str] = set()
    for topic in selected_topics or []:
        destination = selected_topic_destination(str(topic), topic_rules)
        if destination is None:
            continue
        key = os.path.normcase(str(destination))
        if key not in seen:
            destinations.append(destination)
            seen.add(key)
    return destinations


def _validate_route_destination(destination: Path, source: Path) -> None:
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"A custom topic destination exists as a file: {destination}")
    if destination == source or destination in source.parents:
        raise ValueError(
            f"Custom topic destination {destination} cannot be the source folder or an ancestor of it. "
            "Choose a destination inside the source (it will be excluded from scanning) or elsewhere."
        )
    if any(part.casefold() in PROTECTED_DIRECTORY_NAMES for part in destination.parts):
        raise ValueError(f"Custom topic destination is inside a protected system/dependency folder: {destination}")


def scan_directory(
    source_root: Path,
    output_root: Path,
    selected_categories: Iterable[str],
    recursive: bool = True,
    read_contents: bool = True,
    custom_rules: Optional[list] = None,
    progress: Optional[Callable[[str], None]] = None,
    topic_filter_enabled: bool = False,
    selected_topics: Optional[Iterable[str]] = None,
    topic_rules: Optional[list] = None,
    extension_filters: Optional[dict[str, list[str]]] = None,
) -> ScanPlan:
    source = source_root.expanduser().resolve()
    output = output_root.expanduser().resolve()
    if output.exists() and not output.is_dir():
        raise ValueError("The output destination already exists as a file. Choose a folder instead.")
    if output == output.parent:
        raise ValueError("Choose a named destination folder, not the root of a drive or filesystem.")
    if any(part.casefold() in PROTECTED_DIRECTORY_NAMES for part in output.parts):
        raise ValueError("Choose an output folder outside protected Windows/system/dependency directories.")
    selected: Set[str] = set(selected_categories)
    if not source.exists() or not source.is_dir():
        raise ValueError("The source location does not exist or is not a folder.")
    if source.name.casefold() in PROTECTED_DIRECTORY_NAMES:
        raise ValueError("This is a protected system/dependency folder. Choose a normal working folder or drive root instead.")
    try:
        root_names = [item.name for item in source.iterdir() if item.is_dir()]
        root_files = [item.name for item in source.iterdir() if item.is_file()]
        if (source / ".git").exists() or _is_project_root(source, root_names, root_files):
            raise ValueError("The selected source appears to be a software project root. Choose a folder outside the project so relative paths are not broken.")
    except PermissionError:
        raise ValueError("Windows denied access to the selected source folder. Choose a folder you can read.")
    if not selected:
        raise ValueError("Select at least one file category.")
    if _unsafe_output_overlap(source, output):
        raise ValueError("For safety, the output folder cannot be the same as or above the source folder. Choose a folder below the source or on another location.")

    normalized_extension_filters = normalize_extension_filters(extension_filters or {})
    plan = ScanPlan(source, output, sorted(selected), selected_extension_filters=normalized_extension_filters)
    rules = custom_rules or []
    route_destinations = _selected_route_destinations(selected_topics, topic_rules) if topic_filter_enabled else []
    for route_destination in route_destinations:
        _validate_route_destination(route_destination, source)
    checked = 0
    discovery_candidates: list[tuple[Path, str]] = []

    def report(message: str) -> None:
        if progress:
            progress(message)

    def on_walk_error(error: OSError) -> None:
        plan.warnings.append(f"Could not access folder: {error}")

    for current, dirs, filenames in os.walk(source, topdown=True, followlinks=False, onerror=on_walk_error):
        current_path = Path(current)
        try:
            current_resolved = current_path.resolve()
        except OSError:
            current_resolved = current_path
        if current_resolved == output or output in current_resolved.parents:
            dirs[:] = []
            continue
        if any(current_resolved == route or route in current_resolved.parents for route in route_destinations):
            dirs[:] = []
            continue
        if current_path != source and current_path.name.casefold() in PROTECTED_DIRECTORY_NAMES:
            dirs[:] = []
            continue

        # A .git directory is removed from traversal below, but its presence still marks a project root.
        has_git_directory = any(name.casefold() == ".git" for name in dirs)
        safe_dirs = []
        for dirname in dirs:
            child = current_path / dirname
            try:
                child_resolved = child.resolve()
            except OSError:
                child_resolved = child
            if child_resolved == output or any(child_resolved == route or route in child_resolved.parents for route in route_destinations):
                plan.skipped_count += 1
                continue
            if dirname.casefold() in PROTECTED_DIRECTORY_NAMES or _is_reparse_or_link(child):
                plan.skipped_count += 1
                continue
            safe_dirs.append(dirname)
        dirs[:] = safe_dirs if recursive else []

        # Avoid moving files from software projects where relative paths matter.
        if current_path != source and (has_git_directory or _is_project_root(current_path, dirs, filenames)):
            dirs[:] = []
            plan.skipped_count += len(filenames)
            plan.warnings.append(f"Skipped likely project directory to protect its internal structure: {current_path}")
            continue

        for filename in filenames:
            path = current_path / filename
            checked += 1
            plan.scanned_count += 1
            if checked % 250 == 0:
                report(f"Scanned {checked:,} files; found {len(plan.files):,} matching files...")
            if filename.casefold() in PROTECTED_FILE_NAMES or path.suffix.casefold() in PROTECTED_FILE_EXTENSIONS:
                plan.skipped_count += 1
                continue
            if _is_reparse_or_link(path):
                plan.skipped_count += 1
                continue
            try:
                if not path.is_file():
                    plan.skipped_count += 1
                    continue
                category = category_for(path)
                if category not in selected:
                    continue
                if not extension_is_selected(path, category, normalized_extension_filters):
                    continue
                # Collect filename metadata for read-only pattern discovery, even
                # when selective-topic mode later leaves this file unplanned.
                discovery_candidates.append((path, category))
                size = path.stat().st_size
                content = ""
                if read_contents and category == "Documents" and size <= 20 * 1024 * 1024:
                    content = read_document_text(path)
                if topic_filter_enabled:
                    selected_match = classify_selected_topic(path, category, content, selected_topics, rules, topic_rules)
                    if selected_match is None:
                        continue
                    topic, reason, confidence = selected_match
                else:
                    topic, reason, confidence = classify_topic(path, category, content, rules)
                ext_folder = extension_bucket(path)
                custom_destination = selected_topic_destination(topic, topic_rules) if topic_filter_enabled else None
                destination = (custom_destination / path.name) if custom_destination else (output / category / topic / ext_folder / path.name)
                plan.files.append(PlannedFile(
                    source=path,
                    category=category,
                    topic=topic,
                    extension_folder=ext_folder,
                    destination=destination,
                    reason=reason,
                    confidence=confidence,
                    size_bytes=size,
                ))
            except OSError as error:
                plan.skipped_count += 1
                plan.warnings.append(f"Could not inspect {path}: {error}")

        if not recursive:
            break

    plan.discovery_candidates = discovery_candidates
    plan.discovery_groups = discover_repeated_groups(discovery_candidates, rules, topic_rules)
    report(
        f"Scan complete: {len(plan.files):,} files selected from {checked:,} files checked; "
        f"{len(plan.discovery_groups):,} recurring patterns discovered."
    )
    return plan


def scan_directories(
    source_roots: Iterable[Path],
    output_root: Path,
    selected_categories: Iterable[str],
    recursive: bool = True,
    read_contents: bool = True,
    custom_rules: Optional[list] = None,
    progress: Optional[Callable[[str], None]] = None,
    topic_filter_enabled: bool = False,
    selected_topics: Optional[Iterable[str]] = None,
    topic_rules: Optional[list] = None,
    extension_filters: Optional[dict[str, list[str]]] = None,
) -> ScanPlan:
    """Scan multiple selected roots into one shared destination plan.

    Nested or repeated roots are collapsed so that a drive root plus one of its
    child folders does not scan the same files twice. The destination must not
    be inside any selected source root.
    """
    output = output_root.expanduser().resolve()
    if output.exists() and not output.is_dir():
        raise ValueError("The output destination already exists as a file. Choose a folder instead.")
    if output == output.parent:
        raise ValueError("Choose a named destination folder, not the root of a drive or filesystem.")
    if any(part.casefold() in PROTECTED_DIRECTORY_NAMES for part in output.parts):
        raise ValueError("Choose an output folder outside protected Windows/system/dependency directories.")
    requested: List[Path] = []
    seen = set()
    for candidate in source_roots:
        resolved = candidate.expanduser().resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            requested.append(resolved)
    if not requested:
        raise ValueError("Select at least one source drive or folder.")

    # Validate every selected root before scanning any of them. The destination
    # cannot replace or contain a source root, but may be nested inside a source.
    for source in requested:
        if _unsafe_output_overlap(source, output):
            raise ValueError(
                f"For safety, the output folder {output} is the same as or above selected source {source}. "
                "Choose a destination below the source root or at another location."
            )

    # A parent root already includes every child root beneath it.
    requested.sort(key=lambda item: (len(item.parts), os.path.normcase(str(item))))
    normalized: List[Path] = []
    for candidate in requested:
        if any(candidate == parent or parent in candidate.parents for parent in normalized):
            continue
        normalized.append(candidate)

    selected = sorted(set(selected_categories))
    if not selected:
        raise ValueError("Select at least one file category.")

    combined = ScanPlan(
        source_root=normalized[0],
        output_root=output,
        selected_categories=selected,
        source_roots=normalized,
        selected_extension_filters=normalize_extension_filters(extension_filters or {}),
    )
    failures: List[str] = []
    for index, source in enumerate(normalized, start=1):
        if progress:
            progress(f"Scanning source {index:,}/{len(normalized):,}: {source}")
        try:
            part = scan_directory(
                source, output, selected,
                recursive=recursive,
                read_contents=read_contents,
                custom_rules=custom_rules,
                progress=progress,
                topic_filter_enabled=topic_filter_enabled,
                selected_topics=selected_topics,
                topic_rules=topic_rules,
                extension_filters=extension_filters,
            )
            combined.files.extend(part.files)
            combined.discovery_candidates.extend(part.discovery_candidates)
            combined.warnings.extend(part.warnings)
            combined.skipped_count += part.skipped_count
            combined.scanned_count += part.scanned_count
        except (OSError, ValueError) as error:
            message = f"Could not scan selected source {source}: {error}"
            combined.warnings.append(message)
            failures.append(message)

    # A source path can be selected more than once through aliases or mounted
    # paths. Avoid scheduling the exact same resolved pathname twice.
    unique_files = []
    file_keys = set()
    for item in combined.files:
        key = os.path.normcase(str(item.source.resolve()))
        if key in file_keys:
            combined.skipped_count += 1
            continue
        file_keys.add(key)
        unique_files.append(item)
    combined.files = unique_files
    unique_candidates: dict[str, tuple[Path, str]] = {}
    for candidate_path, candidate_category in combined.discovery_candidates:
        candidate_key = os.path.normcase(str(candidate_path))
        unique_candidates[candidate_key] = (candidate_path, candidate_category)
    combined.discovery_candidates = list(unique_candidates.values())
    combined.discovery_groups = discover_repeated_groups(
        combined.discovery_candidates, custom_rules, topic_rules
    )

    if not combined.files and failures:
        raise ValueError("None of the selected sources could be scanned. " + failures[0])
    if progress:
        progress(
            f"Multi-drive scan complete: {len(combined.files):,} matching files from "
            f"{len(normalized):,} source(s); {combined.scanned_count:,} files checked."
        )
    return combined
