from __future__ import annotations

import json
import os
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Iterable

# Everyday formats first, followed by less common and specialist formats.
FILE_TYPE_GROUPS: dict[str, dict[str, list[str]]] = {
    "Documents": {
        "common": ".pdf .docx .xlsx .xls .csv .pptx .doc .txt .ppt .rtf".split(),
        "additional": ".odt .ods .odp .xlsm .md .tsv .json .xml .html .htm .yaml .yml .log .tex .epub .eml .msg".split(),
    },
    "Images": {
        "common": ".jpg .jpeg .png .webp .gif .bmp .tif .tiff".split(),
        "additional": ".heic .heif .svg .ico .raw .dng .cr2 .nef .arw .psd .ai .eps".split(),
    },
    "Videos": {
        "common": ".mp4 .mov .mkv .avi .webm .wmv .m4v".split(),
        "additional": ".mpeg .mpg .3gp .mts .m2ts .flv .vob".split(),
    },
    "Audio": {
        "common": ".mp3 .wav .m4a .flac .aac .ogg .opus".split(),
        "additional": ".oga .wma .aiff .aif .alac .ape .mid .midi".split(),
    },
    "Archives": {
        "common": ".zip .7z .rar .tar .gz".split(),
        "additional": ".bz2 .xz .tgz .iso .cab .zst".split(),
    },
    "Code": {
        "common": ".py .js .ts .css .ps1 .sql".split(),
        "additional": ".jsx .tsx .scss .java .c .cpp .h .hpp .cs .go .rs .php .rb .sh .bat .cmd .ipynb .vue .svelte .toml .ini".split(),
    },
    "Applications": {
        "common": ".exe .msi .msix .apk".split(),
        "additional": ".appx .dmg .deb .rpm .app .com .scr".split(),
    },
    "Fonts": {
        "common": ".ttf .otf .woff2 .woff".split(),
        "additional": ".eot".split(),
    },
    "3D Models": {
        "common": ".stl .obj .fbx .glb .gltf .blend".split(),
        "additional": ".dae .3ds .step .stp .iges .igs .3mf".split(),
    },
    "Others": {
        "common": ".bin .dat .bak .db".split(),
        "additional": ".cfg .conf .sqlite .torrent .ics .vcf .pst .ost".split(),
    },
}


def supported_extensions(category: str) -> list[str]:
    group = FILE_TYPE_GROUPS.get(category, {})
    return list(group.get("common", [])) + list(group.get("additional", []))


def normalize_extension_filters(value: object) -> dict[str, list[str]]:
    """Validate category -> extension subsets. Missing categories mean all formats."""
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, list[str]] = {}
    for category, raw in value.items():
        if category not in FILE_TYPE_GROUPS or not isinstance(raw, list):
            continue
        valid = set(supported_extensions(category))
        selected = {
            (str(item).strip().casefold() if str(item).strip().startswith(".") else "." + str(item).strip().casefold())
            for item in raw if str(item).strip()
        } & valid
        if selected and selected != valid:
            cleaned[category] = [ext for ext in supported_extensions(category) if ext in selected]
    return cleaned


def extension_is_selected(path: Path, category: str, filters: object = None) -> bool:
    if not isinstance(filters, dict) or category not in filters:
        return True
    allowed = filters.get(category)
    if not isinstance(allowed, (list, tuple, set)):
        return True
    return path.suffix.casefold() in {str(item).casefold() for item in allowed}


def extension_filter_summary(categories: Iterable[str], filters: object = None) -> str:
    normalized = normalize_extension_filters(filters or {})
    values = [f"{name}: {len(normalized[name])} selected" if name in normalized else f"{name}: all formats" for name in categories]
    return "No file families selected" if not values else "   |   ".join(values)


def extension_filters_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "SmartDriveOrganizer" / "file_type_filters.json"


def load_extension_filters(path: Path | None = None) -> dict[str, list[str]]:
    try:
        return normalize_extension_filters(json.loads((path or extension_filters_path()).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def save_extension_filters(filters: object, path: Path | None = None) -> Path:
    target = path or extension_filters_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    cleaned = normalize_extension_filters(filters)
    fd, temp_name = tempfile.mkstemp(prefix=".file-types-", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(cleaned, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return target


class FileTypeSelectionDialog(tk.Toplevel):
    """Second-stage picker: All supported formats or a saved extension subset."""
    def __init__(self, parent: tk.Misc, categories: Iterable[str], current_filters: object = None):
        super().__init__(parent)
        self.title("Choose specific file formats")
        self.geometry("780x680")
        self.minsize(650, 520)
        self.transient(parent)
        self.grab_set()
        self.result: dict[str, list[str]] | None = None
        self.categories = [name for name in categories if name in FILE_TYPE_GROUPS]
        self.current_filters = normalize_extension_filters(current_filters or {})
        self.mode_vars: dict[str, tk.StringVar] = {}
        self.extension_vars: dict[str, dict[str, tk.BooleanVar]] = {}
        self.checkbox_frames: dict[str, list[ttk.Widget]] = {}

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Choose the exact formats to include", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Choose All supported formats or only the formats you select. Common formats appear first; additional and specialist formats are below.", wraplength=720).pack(anchor="w", pady=(5, 10))
        if not self.categories:
            ttk.Label(outer, text="Select at least one file family on the main screen, then open this picker.").pack(anchor="w")
        else:
            notebook = ttk.Notebook(outer)
            notebook.pack(fill="both", expand=True)
            for category in self.categories:
                self._build_category_tab(notebook, category)
        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Save format selection", command=self._save).pack(side="right", padx=(0, 8))

    def _build_category_tab(self, notebook: ttk.Notebook, category: str) -> None:
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text=category)
        mode = tk.StringVar(value="specific" if category in self.current_filters else "all")
        self.mode_vars[category] = mode
        controls = ttk.Frame(tab)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Radiobutton(controls, text="All supported formats", variable=mode, value="all", command=lambda name=category: self._set_checkboxes_enabled(name)).pack(anchor="w")
        ttk.Radiobutton(controls, text="Only the formats I select below", variable=mode, value="specific", command=lambda name=category: self._set_checkboxes_enabled(name)).pack(anchor="w")
        buttons = ttk.Frame(tab)
        buttons.pack(fill="x", pady=(0, 8))
        ttk.Button(buttons, text="Select common formats", command=lambda name=category: self._select_common(name)).pack(side="left")
        ttk.Button(buttons, text="Select all formats", command=lambda name=category: self._select_all(name)).pack(side="left", padx=6)
        ttk.Button(buttons, text="Clear selection", command=lambda name=category: self._clear(name)).pack(side="left")
        shell = ttk.Frame(tab)
        shell.pack(fill="both", expand=True)
        canvas = tk.Canvas(shell, highlightthickness=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        content.bind("<Configure>", lambda _event, c=canvas: c.configure(scrollregion=c.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        existing = set(self.current_filters.get(category, []))
        common = set(FILE_TYPE_GROUPS[category]["common"])
        initial = existing if category in self.current_filters else common
        variables: dict[str, tk.BooleanVar] = {}
        widgets: list[ttk.Widget] = []
        for section, title in (("common", "MOST COMMON / MOST USED"), ("additional", "OTHER / SPECIALIST FORMATS")):
            ttk.Label(content, text=title, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 3))
            for extension in FILE_TYPE_GROUPS[category][section]:
                variable = tk.BooleanVar(value=extension in initial)
                variables[extension] = variable
                widget = ttk.Checkbutton(content, text=extension.upper(), variable=variable)
                widget.pack(anchor="w", padx=(8, 0), pady=1)
                widgets.append(widget)
        self.extension_vars[category] = variables
        self.checkbox_frames[category] = widgets
        self._set_checkboxes_enabled(category)

    def _set_checkboxes_enabled(self, category: str) -> None:
        enabled = self.mode_vars[category].get() == "specific"
        for widget in self.checkbox_frames.get(category, []):
            widget.configure(state="normal" if enabled else "disabled")

    def _select_common(self, category: str) -> None:
        self.mode_vars[category].set("specific")
        common = set(FILE_TYPE_GROUPS[category]["common"])
        for ext, variable in self.extension_vars[category].items():
            variable.set(ext in common)
        self._set_checkboxes_enabled(category)

    def _select_all(self, category: str) -> None:
        self.mode_vars[category].set("all")
        for variable in self.extension_vars[category].values():
            variable.set(True)
        self._set_checkboxes_enabled(category)

    def _clear(self, category: str) -> None:
        self.mode_vars[category].set("specific")
        for variable in self.extension_vars[category].values():
            variable.set(False)
        self._set_checkboxes_enabled(category)

    def _save(self) -> None:
        if not self.categories:
            self.destroy()
            return
        updated = dict(self.current_filters)
        for category in self.categories:
            if self.mode_vars[category].get() == "all":
                updated.pop(category, None)
                continue
            selected = [ext for ext, variable in self.extension_vars[category].items() if variable.get()]
            if not selected:
                messagebox.showwarning("No file formats selected", f"Choose at least one {category} format, or select All supported formats.", parent=self)
                return
            updated[category] = selected
        self.result = normalize_extension_filters(updated)
        self.destroy()
