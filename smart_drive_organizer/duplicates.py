from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .search_index import SearchIndex

WORD = re.compile(r"[\w]+", re.UNICODE)
VERSION_MARKERS = re.compile(
    r"(?:\b(?:final|draft|revised|revision|rev|version|ver|copy|duplicate|signed|unsigned)\b"
    r"|\b(?:v|ver|version|rev|r)[\s._-]*\d+[a-z]?\b"
    r"|\b20\d{2}(?:[-_. ]?(?:0?[1-9]|1[0-2]))?(?:[-_. ]?(?:0?[1-9]|[12]\d|3[01]))?\b"
    r"|\(\s*\d+\s*\)$)",
    re.IGNORECASE,
)
STOP = set("the and for with from this that have your our was are document documents file files copy final version draft report".split())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _version_key(name: str) -> tuple[str, bool]:
    stem = Path(name).stem.casefold().replace("_", " ").replace("-", " ")
    cleaned = VERSION_MARKERS.sub(" ", stem)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned, cleaned != stem.strip()


def _tokens(text: str) -> set[str]:
    return {
        word for word in WORD.findall(text.casefold())
        if len(word) >= 3 and word not in STOP and not word.isdigit()
    }


def analyze_duplicates(database: Path | None = None,
                       max_records: int = 12000,
                       similarity_threshold: float = 0.92,
                       progress=None) -> dict[str, Any]:
    """Find exact byte duplicates, likely revisions and near-identical text files.

    This function only reads files and the local index. It never deletes, renames,
    moves or replaces any item.
    """
    index = SearchIndex(database)
    records = index.all_records(max_records)
    index.close()
    records = [row for row in records if Path(row["path"]).is_file()]

    exact_map: dict[str, list[dict]] = defaultdict(list)
    hashes: dict[str, str] = {}
    for number, row in enumerate(records, start=1):
        try:
            digest = sha256_file(Path(row["path"]))
            hashes[row["path"]] = digest
            exact_map[digest].append(row)
        except OSError:
            continue
        if progress and number % 250 == 0:
            progress(f"Checked file hashes: {number:,}/{len(records):,}.")

    exact = []
    for digest, files in exact_map.items():
        if len(files) > 1:
            exact.append({
                "kind": "Exact duplicates",
                "match": "Identical SHA-256 file content",
                "count": len(files),
                "files": files,
                "similarity": 1.0,
                "hash": digest,
            })

    version_map: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in records:
        key, marked = _version_key(row["name"])
        if key and marked:
            version_map[(row["category"], row["extension"], key)].append(row)
    versions = []
    for (category, extension, key), files in version_map.items():
        unique = {row["path"]: row for row in files}
        if len(unique) > 1:
            versions.append({
                "kind": "Possible document versions",
                "match": f"Related filename with version/date/copy markers removed: {key}",
                "count": len(unique),
                "files": list(unique.values()),
                "similarity": None,
            })

    # Near-duplicate text analysis is bounded to indexed text and rare-word
    # candidate pairs; it does not compare every document with every other one.
    docs = [row for row in records if row["category"] == "Documents" and len(row.get("body", "")) >= 120]
    token_sets = {row["path"]: _tokens(row.get("body", "")) for row in docs}
    token_sets = {path: values for path, values in token_sets.items() if len(values) >= 20}
    rows_by_path = {row["path"]: row for row in docs}
    postings: dict[str, list[str]] = defaultdict(list)
    for path, values in token_sets.items():
        for word in values:
            postings[word].append(path)
    max_posting = max(4, int(len(token_sets) * 0.20))
    candidate_pairs: set[tuple[str, str]] = set()
    for word, paths in postings.items():
        if len(paths) < 2 or len(paths) > max_posting:
            continue
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                a, b = sorted((paths[i], paths[j]))
                if hashes.get(a) and hashes.get(a) == hashes.get(b):
                    continue
                candidate_pairs.add((a, b))
                if len(candidate_pairs) >= 15000:
                    break
            if len(candidate_pairs) >= 15000:
                break
        if len(candidate_pairs) >= 15000:
            break

    near_edges: list[tuple[str, str, float]] = []
    for a, b in candidate_pairs:
        left, right = token_sets[a], token_sets[b]
        # A quick length ratio gate avoids matching tiny excerpts to long documents.
        ratio = min(len(left), len(right)) / max(len(left), len(right))
        if ratio < 0.75:
            continue
        score = len(left & right) / max(1, len(left | right))
        if score >= similarity_threshold:
            near_edges.append((a, b, score))

    parent: dict[str, str] = {}
    def find(value: str) -> str:
        parent.setdefault(value, value)
        if parent[value] != value:
            parent[value] = find(parent[value])
        return parent[value]
    def union(left: str, right: str) -> None:
        a, b = find(left), find(right)
        if a != b: parent[b] = a
    for a, b, _score in near_edges:
        union(a, b)
    near_map: dict[str, list[str]] = defaultdict(list)
    for path in parent:
        near_map[find(path)].append(path)
    near = []
    edge_scores = {(a, b): score for a, b, score in near_edges}
    for paths in near_map.values():
        if len(paths) < 2:
            continue
        group_scores = []
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                a, b = sorted((paths[i], paths[j]))
                if (a, b) in edge_scores:
                    group_scores.append(edge_scores[(a, b)])
        near.append({
            "kind": "Near-identical document content",
            "match": "High text-token overlap; check whether these are copies or revisions",
            "count": len(paths),
            "files": [rows_by_path[path] for path in paths],
            "similarity": round(sum(group_scores) / len(group_scores), 3) if group_scores else None,
        })

    if progress:
        progress(f"Duplicate analysis complete: {len(exact)} exact, {len(versions)} version and {len(near)} near-identical groups.")
    return {
        "records_checked": len(records),
        "exact": exact,
        "versions": versions,
        "near": near,
        "total_groups": len(exact) + len(versions) + len(near),
    }
