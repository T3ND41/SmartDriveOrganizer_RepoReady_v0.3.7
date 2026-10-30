from __future__ import annotations
import hashlib
import os, re
from pathlib import Path
from typing import Iterable, Optional
from .classifier import BUILTIN_RULES, SELECTIVE_TOPIC_KEYWORDS, normalize_text
from .models import DiscoveryGroup

STOP = set("""
the and for from with without into onto this that these those your our their
are was were has have had not but can will all any one two three per each
file files document documents attachment attachments copy copies final draft
new old scan scanned scans export exported backup backups temp temporary
untitled unknown other others version revision rev page pages part sample
image images photo photos picture pictures report reports record records data
form forms office desktop download downloads project projects archive archives
folder folders january february march april may june july august september
october november december monday tuesday wednesday thursday friday saturday sunday
""".split())
TOKEN = re.compile(r"[A-Za-z]+")


def _known(custom_rules: Optional[list], topic_rules: Optional[list]) -> set[str]:
    values = {normalize_text(k) for r in BUILTIN_RULES for k in r.get("keywords", [])}
    values.update(normalize_text(k) for group in SELECTIVE_TOPIC_KEYWORDS.values() for k in group)
    for collection in (custom_rules or [], topic_rules or []):
        for rule in collection:
            if isinstance(rule, dict):
                words = rule.get("keywords", [])
                if isinstance(words, str):
                    words = re.split(r"[,\n;]+", words)
                if isinstance(words, list):
                    values.update(normalize_text(str(w)) for w in words if str(w).strip())
    return {v for v in values if v}


def _tokens(stem: str) -> list[tuple[str, str]]:
    result = []
    for raw in TOKEN.findall(stem):
        key = normalize_text(raw)
        acronym = raw.isupper() and 3 <= len(raw) <= 10
        if not key or key in STOP or (len(key) < 5 and not acronym) or len(key) > 24:
            continue
        result.append((key, raw if acronym else raw.title()))
    return result


def discover_repeated_groups(candidates: Iterable[tuple[Path, str]],
                              custom_rules: Optional[list] = None,
                              topic_rules: Optional[list] = None,
                              min_files: int = 2, max_groups: int = 60) -> list[DiscoveryGroup]:
    """Count repeated filename patterns across distinct scanned files, read-only."""
    min_files = max(2, min_files)
    known = _known(custom_rules, topic_rules)
    known_single_terms = {word for phrase in known for word in phrase.split()}
    # Keep only counts and up to five examples per pattern. Avoid a path set for
    # every phrase, which would consume excessive memory on large drives.
    counts: dict[tuple[str, str], dict] = {}
    seen_files: set[str] = set()
    for path, category in candidates:
        path = Path(path)
        path_key = os.path.normcase(str(path))
        if path_key in seen_files:
            continue
        seen_files.add(path_key)
        # A very long descriptive filename can otherwise produce thousands of n-grams.
        words = _tokens(path.stem)[:20]
        keys: dict[str, list[str]] = {}
        for size in (1, 2, 3):
            for i in range(max(0, len(words) - size + 1)):
                part = words[i:i + size]
                phrase = " ".join(w[0] for w in part)
                if not phrase or phrase in known or (size == 1 and phrase in known_single_terms):
                    continue
                keys[phrase] = [w[1] for w in part]
        for phrase, display in keys.items():
            row = counts.setdefault((category, phrase), {"count": 0, "display": display, "samples": [], "fingerprint": hashlib.sha256()})
            row["count"] += 1
            row["fingerprint"].update(path_key.encode("utf-8", errors="surrogatepass") + b"\\0")
            if len(row["samples"]) < 5:
                row["samples"].append(path)

    ranked = []
    for (category, phrase), row in counts.items():
        if row["count"] >= min_files:
            ranked.append((category, phrase, row["count"], row["display"], row["samples"], row["fingerprint"].digest()))
    ranked.sort(key=lambda x: (-x[2], -len(x[1].split()), -len(x[1]), x[0].casefold(), x[1]))

    # Collapse exact-looking duplicates using count and a small sample signature.
    seen: set[tuple] = set()
    result: list[DiscoveryGroup] = []
    for category, phrase, count, display, samples, fingerprint in ranked:
        signature = (category, count, fingerprint)
        if signature in seen:
            continue
        seen.add(signature)
        label = " ".join(display)
        if len(display) == 1 and display[0].isupper() and not display[0].endswith("S"):
            label += "s"
        result.append(DiscoveryGroup(
            phrase, label, category, count,
            [p.name for p in samples], [str(p.parent) for p in samples],
        ))
        if len(result) >= max_groups:
            break
    return result
