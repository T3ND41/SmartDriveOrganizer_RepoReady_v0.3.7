from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


EXTENSION_CATEGORIES: Dict[str, str] = {}

def _add(category: str, extensions: str) -> None:
    for ext in extensions.split():
        EXTENSION_CATEGORIES[ext.lower()] = category


_add("Documents", ".pdf .doc .docx .odt .rtf .txt .md .csv .tsv .xls .xlsx .xlsm .ods .ppt .pptx .odp .json .xml .html .htm .yaml .yml .log .tex .epub .eml .msg")
_add("Images", ".jpg .jpeg .png .gif .bmp .tif .tiff .webp .heic .heif .svg .raw .cr2 .nef .arw .dng .ico .psd .ai .eps")
_add("Videos", ".mp4 .m4v .mov .avi .mkv .wmv .webm .mpeg .mpg .3gp .mts .m2ts .ts .flv .vob")
_add("Audio", ".mp3 .wav .flac .aac .m4a .ogg .oga .opus .wma .aiff .aif .alac .ape .mid .midi")
_add("Archives", ".zip .rar .7z .tar .gz .bz2 .xz .tgz .iso .cab .zst")
_add("Code", ".py .js .ts .jsx .tsx .css .scss .java .c .cpp .h .hpp .cs .go .rs .php .rb .sh .ps1 .bat .cmd .sql .ipynb .vue .svelte .toml .ini")
_add("Applications", ".exe .msi .msix .appx .apk .dmg .deb .rpm .app .com .scr")
_add("Fonts", ".ttf .otf .woff .woff2 .eot")
_add("3D Models", ".stl .obj .fbx .gltf .glb .blend .dae .3ds .step .stp .iges .igs .3mf")

# Built-in, deterministic phrase rules. More specific phrases are tested first.
BUILTIN_RULES: List[Dict[str, Any]] = [
    {"name": "Monthly Statements", "keywords": ["monthly statement", "monthly statements", "bank statement", "bank statements", "account statement", "account statements"]},
    {"name": "Delivery Notes", "keywords": ["delivery note", "delivery notes", "delivery-note", "delivery-notes", "proof of delivery"]},
    {"name": "Purchase Orders", "keywords": ["purchase order", "purchase orders", "po number", "po-"]},
    {"name": "Purchase Requisitions", "keywords": ["purchase requisition", "purchase requisitions"]},
    {"name": "Requisitions", "keywords": ["requisition", "requisitions", "requisition form", "requisition request", "site requisition", "material requisition", "store requisition"]},
    {"name": "Invoices", "keywords": ["tax invoice", "proforma invoice", "pro forma invoice", "sales invoice", "purchase invoice", "invoice", "invoices"]},
    {"name": "Quotations", "keywords": ["quotation", "quotations", "quote", "quotes", "rfq", "request for quotation"]},
    {"name": "Tenders", "keywords": ["tender", "tenders", "bid submission", "tender submission", "tender document"]},
    {"name": "Receipts", "keywords": ["payment receipt", "cash receipt", "receipt", "receipts"]},
    {"name": "Contracts", "keywords": ["employment contract", "service contract", "contract", "contracts", "agreement"]},
    {"name": "Payslips", "keywords": ["payslip", "pay slip", "salary slip", "payroll"]},
    {"name": "Tax Documents", "keywords": ["tax return", "tax clearance", "tax certificate", "tax document", "zra"]},
    {"name": "Reports", "keywords": ["monthly report", "weekly report", "annual report", "inspection report", "report", "reports"]},
    {"name": "Certificates", "keywords": ["certificate", "certificates", "qualification", "qualifications"]},
    {"name": "Manuals", "keywords": ["user manual", "operation manual", "maintenance manual", "manual", "manuals", "datasheet", "data sheet"]},
    {"name": "Company Profiles", "keywords": ["company profile", "company profiles", "capability statement"]},
    {"name": "Curriculum Vitae", "keywords": ["curriculum vitae", "cv", "resume", "résumé"]},
    {"name": "Meeting Records", "keywords": ["meeting minutes", "minutes of meeting", "meeting notes"]},
    {"name": "Drawings", "keywords": ["technical drawing", "engineering drawing", "drawing", "drawings", "layout plan"]},
    {"name": "Presentations", "keywords": ["presentation", "presentations", "slide deck"]},
    {"name": "Photographs", "keywords": ["photograph", "photographs", "photo", "photos", "pictures"]},
    {"name": "Screenshots", "keywords": ["screenshot", "screenshots", "screen capture"]},
    {"name": "Training Videos", "keywords": ["training video", "training videos", "tutorial video"]},
    {"name": "Music", "keywords": ["soundtrack", "music", "song", "songs", "audio recording"]},
]


def normalize_text(value: str) -> str:
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"[_\-./\\]+", " ", value)
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())




# Curated selective-organization groups. These deliberately collapse specific
# built-in labels (for example "Monthly Statements") into one user-selected
# destination ("Statements") when selective mode is enabled.
SELECTIVE_TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "Statements": [
        "statement", "statements", "monthly statement", "monthly statements",
        "bank statement", "bank statements", "account statement",
        "account statements", "statement of account", "statement of accounts",
        "financial statement", "financial statements",
    ],
    "Requisitions": [
        "requisition", "requisitions", "purchase requisition",
        "purchase requisitions", "material requisition", "material requisitions",
        "site requisition", "site requisitions", "store requisition",
        "store requisitions", "requisition form", "requisition request",
    ],
    "Quotations": [
        "quotation", "quotations", "quote", "quotes", "rfq",
        "request for quotation", "request for quotations",
        "supplier quotation", "supplier quotations", "price quotation",
    ],
}


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = normalize_text(phrase)
    if not normalized_phrase:
        return False
    return f" {normalized_phrase} " in f" {text} "


def normalize_topic_rules(rules: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate user-defined selective topic rules.

    Each rule has a folder ``name``, one or more ``keywords`` and a ``categories``
    scope. ``["Any"]`` applies to all supported file categories.
    """
    valid_categories = {
        "Documents", "Images", "Videos", "Audio", "Archives", "Code",
        "Applications", "Fonts", "3D Models", "Others", "Any",
    }
    cleaned: List[Dict[str, Any]] = []
    seen_names = set()
    for item in rules:
        if not isinstance(item, dict):
            continue
        name = safe_folder_name(str(item.get("name", "")))
        if not name or name == "Unclassified":
            continue
        keywords_value = item.get("keywords", [])
        if isinstance(keywords_value, str):
            keywords = [part.strip() for part in re.split(r"[,\n;]+", keywords_value) if part.strip()]
        elif isinstance(keywords_value, list):
            keywords = [str(part).strip() for part in keywords_value if str(part).strip()]
        else:
            keywords = []
        # De-duplicate phrases without changing the user's original wording.
        unique_keywords = []
        seen_keywords = set()
        for keyword in keywords:
            key = normalize_text(keyword)
            if key and key not in seen_keywords:
                unique_keywords.append(keyword)
                seen_keywords.add(key)
        categories_value = item.get("categories", item.get("category", "Any"))
        if isinstance(categories_value, str):
            categories = [categories_value]
        elif isinstance(categories_value, list):
            categories = [str(value) for value in categories_value]
        else:
            categories = ["Any"]
        categories = [value for value in categories if value in valid_categories]
        if not categories:
            categories = ["Any"]
        if "Any" in categories:
            categories = ["Any"]
        destination = str(item.get("destination", "") or "").strip()
        match_mode_value = str(item.get("match_mode", "whole_phrase") or "whole_phrase").strip().casefold()
        match_mode = "whole_phrase" if match_mode_value in {"whole", "whole word", "whole words", "whole phrase", "whole_phrase", "exact"} else "contains"
        name_key = name.casefold()
        # Rules with the same folder label are merged; this lets users extend a
        # built-in group such as Requisitions with their own synonyms.
        if name_key in seen_names:
            existing = next(rule for rule in cleaned if rule["name"].casefold() == name_key)
            existing["keywords"] = list(dict.fromkeys(existing["keywords"] + unique_keywords))
            if "Any" in categories or "Any" in existing["categories"]:
                existing["categories"] = ["Any"]
            else:
                existing["categories"] = list(dict.fromkeys(existing["categories"] + categories))
            if destination:
                existing["destination"] = destination
            if match_mode == "contains":
                existing["match_mode"] = "contains"
            continue
        if unique_keywords:
            cleaned.append({
                "name": name,
                "keywords": unique_keywords,
                "categories": categories,
                "destination": destination,
                "match_mode": match_mode,
            })
            seen_names.add(name_key)
    return cleaned


def load_topic_rules(path: Path) -> List[Dict[str, Any]]:
    """Load custom selective-topic groups from the user's app-data folder."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return normalize_topic_rules(data)
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return []


def save_topic_rules(path: Path, rules: Iterable[Dict[str, Any]]) -> None:
    """Atomically save custom selective-topic groups."""
    cleaned = normalize_topic_rules(rules)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def selected_topic_rule(topic: str, topic_rules: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Return the normalized user rule for a selected topic, if one exists."""
    key = normalize_text(topic)
    for rule in normalize_topic_rules(topic_rules or []):
        if normalize_text(rule.get("name", "")) == key:
            return rule
    return None


def selected_topic_destination(topic: str, topic_rules: Optional[List[Dict[str, Any]]] = None) -> Optional[Path]:
    """Return a user-selected exact destination folder for a topic rule."""
    rule = selected_topic_rule(topic, topic_rules)
    destination = str((rule or {}).get("destination", "")).strip()
    if not destination:
        return None
    return Path(os.path.expandvars(destination)).expanduser().resolve()


def selected_topic_destinations(selected_topics: Optional[Iterable[str]], topic_rules: Optional[List[Dict[str, Any]]] = None) -> List[Path]:
    """Return unique exact destination folders belonging to selected topic rules."""
    result: List[Path] = []
    seen = set()
    for topic in selected_topics or []:
        destination = selected_topic_destination(str(topic), topic_rules)
        if destination is None:
            continue
        key = os.path.normcase(str(destination))
        if key not in seen:
            result.append(destination)
            seen.add(key)
    return result


def _keyword_matches(text: str, phrase: str, match_mode: str = "whole_phrase") -> bool:
    if not text or not phrase:
        return False
    if match_mode == "contains":
        # Also compact spaces so an entered code such as Q-U-O (normalized to
        # "q u o") matches the same letters inside "quotation".
        compact_text = re.sub(r"\s+", "", text)
        compact_phrase = re.sub(r"\s+", "", phrase)
        return phrase in text or (bool(compact_phrase) and compact_phrase in compact_text)
    return _contains_phrase(text, phrase)


def classify_selected_topic(
    path: Path,
    category: str,
    content_text: str = "",
    selected_topics: Optional[Iterable[str]] = None,
    custom_rules: Optional[List[Dict[str, Any]]] = None,
    topic_rules: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Tuple[str, str, float]]:
    """Classify a file into one explicitly selected topic group.

    Filename phrase matching works for every supported file category. For
    Documents, callers may pass extracted document text for an additional
    content match. The caller must leave nonmatching files untouched.
    """
    selected = [safe_folder_name(str(item)) for item in (selected_topics or []) if str(item).strip()]
    if not selected:
        return None

    filename_text = normalize_text(path.stem)
    body_text = normalize_text(content_text[:12000]) if content_text and category == "Documents" else ""
    topic_rules = normalize_topic_rules(topic_rules or [])
    matches: List[Tuple[int, int, int, str, str, str]] = []

    for selected_name in selected:
        canonical = safe_folder_name(selected_name)
        keywords = list(SELECTIVE_TOPIC_KEYWORDS.get(canonical, [])) if category == "Documents" else []
        for rule in topic_rules:
            if rule["name"].casefold() != canonical.casefold():
                continue
            scopes = rule.get("categories", ["Any"])
            if "Any" not in scopes and category not in scopes:
                continue
            keywords.extend(rule.get("keywords", []))

        # Preserve backwards compatibility with earlier custom keyword rules
        # whose `name` was the selected folder label.
        for rule in custom_rules or []:
            if not isinstance(rule, dict):
                continue
            if normalize_text(str(rule.get("name", ""))) != normalize_text(canonical):
                continue
            old_scope = str(rule.get("category", "Any"))
            if old_scope not in ("Any", category):
                continue
            raw_keywords = rule.get("keywords", [])
            if isinstance(raw_keywords, list):
                keywords.extend(str(value) for value in raw_keywords if str(value).strip())

        seen_keywords = set()
        user_rule = selected_topic_rule(canonical, topic_rules)
        match_mode = str((user_rule or {}).get("match_mode", "whole_phrase"))
        for keyword in keywords:
            phrase = normalize_text(str(keyword))
            if not phrase or phrase in seen_keywords:
                continue
            seen_keywords.add(phrase)
            if _keyword_matches(filename_text, phrase, match_mode):
                matches.append((1, len(phrase.split()), len(phrase), canonical, str(keyword), "filename"))
            elif body_text and _keyword_matches(body_text, phrase, match_mode):
                matches.append((0, len(phrase.split()), len(phrase), canonical, str(keyword), "document text"))

    if not matches:
        return None
    matches.sort(key=lambda item: (item[0], item[1], item[2], item[3].casefold()), reverse=True)
    filename_match, _, _, topic, keyword, source = matches[0]
    confidence = 0.98 if filename_match else 0.82
    return topic, f"Selected topic '{topic}': matched '{keyword}' in {source}", confidence


def safe_folder_name(value: str) -> str:
    """Return a Windows-safe single folder segment for user-defined topic labels."""
    value = str(value).strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        return "Unclassified"
    if value.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        value = f"_{value}"
    return value[:100].rstrip(" .") or "Unclassified"


def category_for(path: Path) -> str:
    return EXTENSION_CATEGORIES.get(path.suffix.lower(), "Others")


def extension_bucket(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return suffix.upper() if suffix else "NO EXTENSION"


def load_custom_rules(path: Path) -> List[Dict[str, Any]]:
    """Load user-defined phrase rules. Invalid/missing config safely falls back to none."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        cleaned: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            keywords = item.get("keywords", [])
            category = str(item.get("category", "Any")).strip() or "Any"
            if name and isinstance(keywords, list):
                valid = [str(k).strip() for k in keywords if str(k).strip()]
                if valid:
                    cleaned.append({"name": name, "keywords": valid, "category": category})
        return cleaned
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def save_custom_rules(path: Path, rules: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(list(rules), indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def classify_topic(
    path: Path,
    category: str,
    content_text: str = "",
    custom_rules: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str, float]:
    """Return topic folder, explanation, and confidence using filename-first rules."""
    filename_text = normalize_text(path.stem)
    body_text = normalize_text(content_text[:12000]) if content_text else ""
    custom_rules = custom_rules or []

    rules: List[Dict[str, Any]] = []
    for rule in custom_rules:
        rules.append({**rule, "custom": True})
    for rule in BUILTIN_RULES:
        rules.append({**rule, "category": "Any", "custom": False})

    matches: List[Tuple[int, int, int, bool, Dict[str, Any], str]] = []
    for rule in rules:
        target_category = str(rule.get("category", "Any"))
        if target_category not in ("Any", category):
            continue
        for keyword in rule.get("keywords", []):
            phrase = normalize_text(str(keyword))
            if not phrase:
                continue
            if f" {phrase} " in f" {filename_text} ":
                matches.append((1, len(phrase.split()), len(phrase), bool(rule.get("custom")), rule, str(keyword)))
            elif body_text and f" {phrase} " in f" {body_text} ":
                matches.append((0, len(phrase.split()), len(phrase), bool(rule.get("custom")), rule, str(keyword)))

    if matches:
        matches.sort(key=lambda m: (m[0], m[1], m[2], m[3]), reverse=True)
        filename_match, _, _, _, rule, keyword = matches[0]
        source = "filename" if filename_match else "document text"
        confidence = 0.98 if source == "filename" else 0.82
        label = str(rule.get("name", "Unclassified")).strip()
        return safe_folder_name(label), f"Matched '{keyword}' in {source}", confidence

    defaults = {
        "Documents": "Unclassified Documents",
        "Images": "Unclassified Images",
        "Videos": "Unclassified Videos",
        "Audio": "Unclassified Audio",
        "Archives": "Unclassified Archives",
        "Code": "Unclassified Code",
        "Applications": "Unclassified Applications",
        "Fonts": "Unclassified Fonts",
        "3D Models": "Unclassified 3D Models",
        "Others": "Unclassified Files",
    }
    return safe_folder_name(defaults.get(category, "Unclassified Files")), "No matching keyword rule; placed in unclassified group", 0.35
