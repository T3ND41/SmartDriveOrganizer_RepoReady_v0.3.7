from __future__ import annotations

import os
import queue
import subprocess
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from .duplicates import analyze_duplicates, recycle_exact_duplicates
from .search_index import SearchIndex, build_index
from .operation_control import OperationCancelled, OperationControl
from .theme import apply_dialog_theme


def _open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        webbrowser.open(path.as_uri())


def _show_in_folder(path: Path) -> None:
    if os.name == "nt":
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        _open_path(path.parent)


def _size(value: int) -> str:
    amount = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{int(amount)} B" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


class DuplicateReviewDialog(tk.Toplevel):
    """Inspection-only review of exact copies, possible versions and similar text."""
    def __init__(self, parent: tk.Misc, result: dict):
        super().__init__(parent)
        self.title("Duplicate and version review")
        self.geometry("1000x700")
        self.minsize(820, 560)
        self.transient(parent)
        self.grab_set()
        self.groups = result.get("exact", []) + result.get("versions", []) + result.get("near", [])
        self.active_files: list[dict] = []
        palette = apply_dialog_theme(self, parent)
        self.brand_palette = palette
        self.theme_name = getattr(parent, "theme_name", "light")
        bg, card, ink, black, white, red, muted = (
            palette["bg"], palette["card"], palette["ink"], palette["black"],
            palette["white"], palette["red"], palette["muted"],
        )
        self.configure(bg=bg)
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=ink, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=bg, foreground=ink, font=("Segoe UI", 18, "bold"))
        style.configure("Treeview", rowheight=27, font=("Segoe UI", 9), background=card, fieldbackground=card, foreground=ink)
        style.configure("Treeview.Heading", background=black, foreground=white, font=("Segoe UI", 9, "bold"), padding=7)
        style.configure("Primary.TButton", background=red, foreground=white, font=("Segoe UI", 9, "bold"), padding=9)
        style.configure("Exact.TLabelframe", background=card, bordercolor=red, borderwidth=2, relief="solid")
        style.configure("Exact.TLabelframe.Label", background=card, foreground=red, font=("Segoe UI", 9, "bold"))
        outer = ttk.Frame(self, padding=14); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Review possible duplicates and revisions", style="Title.TLabel").pack(anchor="w")
        coverage = (
            f"Checked {result.get('records_checked', 0):,} of {result.get('index_total', result.get('records_checked', 0)):,} indexed files; "
            f"found {result.get('total_groups', 0):,} groups. "
            "No files were changed or deleted."
        )
        if result.get("truncated"):
            coverage += " The analysis reached its 50,000-file review limit, so some indexed files were not included."
        ttk.Label(outer, text=coverage, wraplength=940).pack(anchor="w", pady=(5, 12))
        body = ttk.Frame(outer); body.pack(fill="both", expand=True)
        left = ttk.Frame(body); left.pack(side="left", fill="both", expand=True)
        self.tree = ttk.Treeview(left, columns=("kind", "count", "similarity", "match"), show="headings", height=16)
        for col, title, width in (("kind", "Finding", 190), ("count", "Files", 55), ("similarity", "Similarity", 80), ("match", "Why grouped", 330)):
            self.tree.heading(col, text=title); self.tree.column(col, width=width, minwidth=55)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        details = ttk.LabelFrame(body, text="Files in selected group", padding=8)
        details.pack(side="left", fill="both", padx=(10, 0))
        self.file_list = tk.Listbox(details, width=52, height=8, font=("Segoe UI", 8), bg=card, fg=ink, selectbackground=red, selectforeground=white, highlightthickness=1, highlightbackground=palette["border"])
        self.file_list.pack(fill="x", expand=False)
        self.compare_frame = ttk.Frame(details)
        self.compare_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.compare_vars = [tk.StringVar(value="Select a group to compare its files.") for _ in range(2)]
        self.compare_cards = []
        self.compare_titles = []
        for col in range(2):
            card = ttk.LabelFrame(self.compare_frame, text=f"FILE {col + 1}", padding=7)
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 5, 0))
            title = ttk.Label(card, text=f"FILE {col + 1}", foreground=muted, font=("Segoe UI", 8, "bold"))
            title.pack(anchor="w", pady=(0, 5))
            ttk.Label(card, textvariable=self.compare_vars[col], wraplength=205, justify="left").pack(anchor="w")
            self.compare_cards.append(card)
            self.compare_titles.append(title)
        self.compare_frame.columnconfigure(0, weight=1)
        self.compare_frame.columnconfigure(1, weight=1)
        ttk.Label(details, text="Exact matches are verified by SHA-256. No files are changed during review.", foreground=red, wraplength=420).pack(anchor="w", pady=(7, 0))
        self.active_group = None
        self.tree.tag_configure("exact", background=palette["badge"], foreground=red)
        self.tree.tag_configure("version", background=palette["border"], foreground=ink)
        self.tree.tag_configure("near", background=palette["bg"], foreground=muted)
        for i, group in enumerate(self.groups):
            sim = "—" if group.get("similarity") is None else f"{group['similarity']:.0%}"
            kind = str(group.get("kind", ""))
            tag = "exact" if kind == "Exact duplicates" else ("version" if "version" in kind.casefold() else "near")
            self.tree.insert("", "end", iid=str(i), values=(kind, group["count"], sim, group["match"]), tags=(tag,))
        self.tree.bind("<<TreeviewSelect>>", self._select)
        self.file_list.bind("<Double-1>", lambda _e: self._open())
        actions = ttk.Frame(outer); actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Open selected file", command=self._open).pack(side="left")
        ttk.Button(actions, text="Show in folder", command=self._reveal).pack(side="left", padx=6)
        self.recycle_button = ttk.Button(actions, text="Keep newest and recycle exact older copies", command=self._recycle_older, state="disabled")
        self.recycle_button.pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")
        if self.groups:
            self.tree.selection_set("0"); self._select()

    def _select(self, _event=None):
        ids = self.tree.selection()
        self.file_list.delete(0, "end")
        self.active_files = []
        self.active_group = None
        self.recycle_button.configure(state="disabled")
        for index, value in enumerate(self.compare_vars):
            value.set("Select a group to compare its files side by side.")
            self.compare_cards[index].configure(style="TLabelframe")
            self.compare_titles[index].configure(foreground=muted, text=f"FILE {index + 1}")
        if not ids:
            return
        group = self.groups[int(ids[0])]
        self.active_group = group
        self.active_files = group.get("files", [])
        exact_match = group.get("kind") == "Exact duplicates" and len(self.active_files) >= 2
        for index, row in enumerate(self.active_files):
            label = str(row["path"])
            self.file_list.insert("end", label)
            if exact_match:
                self.file_list.itemconfig(index, background=self.brand_palette["badge"], foreground=self.brand_palette["red"])
        if len(self.active_files) >= 2:
            ordered = sorted(self.active_files, key=lambda row: (float(row.get("modified_ts", 0) or 0), str(row.get("path", "")).casefold()))
            pair = (ordered[0], ordered[-1]) if exact_match else (self.active_files[0], self.active_files[1])
            for index, row in enumerate(pair):
                modified = row.get("modified_ts")
                try:
                    stamp = datetime.fromtimestamp(float(modified)).strftime("%Y-%m-%d %H:%M:%S") if modified else "Unknown"
                except (OSError, TypeError, ValueError, OverflowError):
                    stamp = "Unknown"
                role = ("OLDER EXACT COPY" if index == 0 else "NEWEST EXACT COPY • KEEP") if exact_match else f"RELATED FILE {index + 1}"
                digest = str(group.get("hash", ""))
                hash_line = f"\nSHA-256: {digest[:20]}…" if exact_match and digest else ""
                self.compare_vars[index].set(
                    f"{row.get('name','')}\n\n{role}\nModified: {stamp}\nSize: {_size(row.get('size_bytes',0))}"
                    f"{hash_line}\n\nOriginal location:\n{row.get('path','')}"
                )
                if exact_match:
                    self.compare_cards[index].configure(style="Exact.TLabelframe")
                    self.compare_titles[index].configure(
                        foreground=red,
                        text="OLDER COPY • REVIEW" if index == 0 else "NEWEST COPY • KEEP",
                    )
            if exact_match:
                if len(ordered) > 2:
                    self.compare_vars[1].set(self.compare_vars[1].get() + f"\n\nPlus {len(ordered)-2:,} additional older exact copy/copies.")
                self.recycle_button.configure(state="normal")

    def _recycle_older(self) -> None:
        group = self.active_group
        if not group or group.get("kind") != "Exact duplicates" or len(group.get("files", [])) < 2:
            return
        files = list(group["files"])
        def modified(row):
            value = row.get("modified_ts")
            try:
                return float(value) if value is not None else Path(row["path"]).stat().st_mtime
            except (OSError, KeyError, TypeError, ValueError):
                return 0.0
        keeper = max(files, key=lambda row: (modified(row), str(row.get("path", "")).casefold()))
        older = [row for row in files if str(row.get("path", "")) != str(keeper.get("path", ""))]
        prompt = (
            "These files were byte-for-byte identical when scanned. The app will verify their SHA-256 again before action.\n\n"
            f"KEEP newest:\n{keeper.get('path','')}\n\n"
            "SEND older exact copies to the Recycle Bin:\n"
            + "\n".join(str(row.get("path", "")) for row in older[:8])
            + (f"\n…and {len(older)-8:,} more." if len(older) > 8 else "")
            + "\n\nThis cannot delete near-matches or possible versions. Continue?"
        )
        if not messagebox.askyesno("Confirm Recycle Bin action", prompt, parent=self, icon="warning"):
            return
        try:
            result = recycle_exact_duplicates(group, keeper["path"])
        except Exception as error:
            messagebox.showerror("Could not recycle duplicates", str(error), parent=self)
            return
        removed = set(result["recycled"])
        group["files"] = [row for row in group["files"] if str(Path(row["path"]).resolve()) not in removed]
        group["count"] = len(group["files"])
        self.file_list.delete(0, "end")
        for row in group["files"]:
            self.file_list.insert("end", row["path"])
        if group["count"] < 2:
            self.tree.delete(self.tree.selection()[0])
            self.recycle_button.configure(state="disabled")
            self.active_group = None
            for value in self.compare_vars:
                value.set("Exact duplicate group resolved.")
        else:
            self.tree.set(self.tree.selection()[0], "count", group["count"])
            self._select()
        details = f"Moved {result['recycled_count']:,} exact duplicate(s) to the Recycle Bin. Kept:\n{result['keeper']}"
        if result["skipped"] or result["errors"]:
            details += "\n\nLeft untouched / errors:\n" + "\n".join((result["skipped"] + result["errors"])[:8])
        messagebox.showinfo("Duplicate review action complete", details, parent=self)

    def _selected_file(self) -> Path | None:
        selection = self.file_list.curselection()
        if not selection: return None
        return Path(self.active_files[selection[0]]["path"])

    def _open(self):
        path = self._selected_file()
        if path and path.is_file():
            _open_path(path)

    def _reveal(self):
        path = self._selected_file()
        if path and path.exists():
            _show_in_folder(path)


class SearchDashboardDialog(tk.Toplevel):
    """Google-style local search with filters, indexing and quick file access."""
    def __init__(self, parent: tk.Misc, categories: list[str]):
        super().__init__(parent)
        self.parent_app = parent
        self.categories = list(categories)
        self.title("Smart Drive Organizer — Search your files")
        self.geometry("1220x790")
        self.minsize(980, 660)
        self.transient(parent)
        self.rows: list[dict] = []
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.operation_control: OperationControl | None = None
        palette = apply_dialog_theme(self, parent)
        bg, white, black, red, muted = (
            palette["bg"], palette["card"], palette["black"],
            palette["red"], palette["muted"],
        )
        ink = palette["ink"]
        self.theme_name = getattr(parent, "theme_name", "light")
        self.configure(bg=bg)
        self.feature_icons = getattr(parent, "feature_icons", {})
        def feature_button(container: tk.Misc, feature: str, **options) -> ttk.Button:
            icon = self.feature_icons.get(feature)
            if icon is not None:
                options["image"] = icon
                options["compound"] = "left"
            return ttk.Button(container, **options)
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=ink, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=bg, foreground=black, font=("Segoe UI", 22, "bold"))
        style.configure("Hint.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
        style.configure("TEntry", padding=8, fieldbackground=white, foreground=ink)
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 7))
        style.configure("Primary.TButton", background=red, foreground=white, font=("Segoe UI", 9, "bold"), padding=(14, 9))
        style.map("Primary.TButton", background=[("active", red)])
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 9), background=white, fieldbackground=white, foreground=ink)
        style.configure("Treeview.Heading", background=black, foreground=white, font=("Segoe UI", 9, "bold"), padding=7)

        outer = ttk.Frame(self, padding=18); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Search everything you have indexed", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Search filenames and extracted text stored locally on this computer. Use filters to narrow results and open the original file location.", style="Hint.TLabel").pack(anchor="w", pady=(4, 12))

        search_row = ttk.Frame(outer); search_row.pack(fill="x", pady=(0, 10))
        self.query_var = tk.StringVar()
        self.query_entry = ttk.Entry(search_row, textvariable=self.query_var, font=("Segoe UI", 13))
        self.query_entry.pack(side="left", fill="x", expand=True)
        self.query_entry.bind("<Return>", lambda _e: self._search())
        feature_button(search_row, "deep-search", text="SEARCH", style="Primary.TButton", command=self._search).pack(side="left", padx=(8, 0))
        feature_button(search_row, "deep-search", text="Build / refresh index", command=self._start_index).pack(side="left", padx=(8, 0))

        filters = ttk.LabelFrame(outer, text="FILTERS", padding=10)
        filters.pack(fill="x", pady=(0, 10))
        for col in range(6): filters.columnconfigure(col, weight=1)
        self.location_var = tk.StringVar()
        self.category_var = tk.StringVar(value="Any")
        self.extension_var = tk.StringVar()
        self.topic_var = tk.StringVar()
        self.date_from_var = tk.StringVar()
        self.date_to_var = tk.StringVar()
        self.min_size_var = tk.StringVar()
        self.max_size_var = tk.StringVar()
        self._field(filters, "Location contains", self.location_var, 0, 0)
        ttk.Label(filters, text="File family").grid(row=0, column=2, sticky="w", padx=5)
        ttk.Combobox(filters, textvariable=self.category_var, values=["Any"] + self.categories, state="readonly", width=16).grid(row=1, column=2, sticky="ew", padx=5, pady=(0, 5))
        self._field(filters, "Extension (e.g. .pdf)", self.extension_var, 0, 3)
        self._field(filters, "Topic / folder", self.topic_var, 0, 4)
        self._field(filters, "Modified after YYYY-MM-DD", self.date_from_var, 2, 0)
        self._field(filters, "Modified before YYYY-MM-DD", self.date_to_var, 2, 1)
        self._field(filters, "Minimum size MB", self.min_size_var, 2, 2)
        self._field(filters, "Maximum size MB", self.max_size_var, 2, 3)
        ttk.Button(filters, text="Clear filters", command=self._clear).grid(row=3, column=5, sticky="e", padx=5, pady=4)

        toolbar = ttk.Frame(outer); toolbar.pack(fill="x", pady=(0, 6))
        self.status_var = tk.StringVar(value="Build or refresh the local index to search file contents.")
        ttk.Label(toolbar, textvariable=self.status_var, style="Hint.TLabel").pack(side="left")
        feature_button(toolbar, "pattern-scan", text="Find duplicates & versions", command=self._start_duplicates).pack(side="right")
        self.cancel_button = ttk.Button(toolbar, text="Cancel", command=self._cancel_operation, state="disabled")
        self.cancel_button.pack(side="right", padx=(6, 0))
        self.pause_button = ttk.Button(toolbar, text="Pause", command=self._toggle_pause, state="disabled")
        self.pause_button.pack(side="right", padx=(6, 0))

        result_frame = ttk.Frame(outer); result_frame.pack(fill="both", expand=True)
        columns = ("name", "category", "extension", "size", "modified", "topic", "location")
        self.tree = ttk.Treeview(result_frame, columns=columns, show="headings", height=18)
        labels = {"name":"File", "category":"Family", "extension":"Format", "size":"Size", "modified":"Modified", "topic":"Topic", "location":"Original location"}
        widths = {"name":210, "category":90, "extension":70, "size":80, "modified":145, "topic":145, "location":420}
        for col in columns:
            self.tree.heading(col, text=labels[col]); self.tree.column(col, width=widths[col], minwidth=55, stretch=(col=="location"))
        yscroll = ttk.Scrollbar(result_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(result_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); yscroll.grid(row=0, column=1, sticky="ns"); xscroll.grid(row=1, column=0, sticky="ew")
        result_frame.rowconfigure(0, weight=3); result_frame.columnconfigure(0, weight=1)
        self.preview = tk.Text(result_frame, height=7, wrap="word", font=("Segoe UI", 9), relief="solid", borderwidth=1, bg=white, fg=ink)
        self.preview.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        self.preview.insert("1.0", "Select a result to preview its indexed text. The preview is stored locally and does not alter the original file.")
        self.preview.configure(state="disabled")
        self.tree.bind("<<TreeviewSelect>>", self._preview_selected)
        self.tree.bind("<Double-1>", lambda _e: self._open())
        actions = ttk.Frame(outer); actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Open file", command=self._open).pack(side="left")
        ttk.Button(actions, text="Show in folder", command=self._reveal).pack(side="left", padx=6)
        self.index_count_var = tk.StringVar(value="Local index")
        ttk.Label(actions, textvariable=self.index_count_var, style="Hint.TLabel").pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._after_id = self.after(100, self._poll)
        self.query_entry.focus_set()
        self._refresh_count()

    @staticmethod
    def _field(parent, label: str, variable: tk.StringVar, row: int, col: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row+1, column=col, sticky="ew", padx=5, pady=(0, 5))

    def _close(self) -> None:
        if self.busy and self.operation_control is not None:
            if not messagebox.askyesno("Close search window", "Cancel the current index/duplicate operation at the next safe checkpoint and close this window?", parent=self):
                return
            self.operation_control.cancel()
        try:
            self.after_cancel(self._after_id)
        except (AttributeError, tk.TclError):
            pass
        self.destroy()

    def _toggle_pause(self) -> None:
        control = self.operation_control
        if not self.busy or control is None:
            return
        if control.paused:
            control.resume()
            self.pause_button.configure(text="Pause")
            self.status_var.set("Resuming…")
        else:
            control.pause()
            self.pause_button.configure(text="Resume")
            self.status_var.set("Paused. Progress is retained until you resume.")

    def _cancel_operation(self) -> None:
        if not self.busy or self.operation_control is None:
            return
        if messagebox.askyesno(
            "Cancel operation",
            "Stop at the next safe checkpoint? Nothing will be deleted or moved by indexing or duplicate analysis.",
            parent=self,
            icon="warning",
        ):
            self.operation_control.cancel()
            self.status_var.set("Cancelling…")

    def _refresh_count(self) -> None:
        try:
            index = SearchIndex()
            count = index.count()
            index.close()
            self.index_count_var.set(f"{count:,} indexed files")
        except Exception as error:
            self.index_count_var.set(f"Index unavailable: {error}")

    def _clear(self) -> None:
        for var in (self.location_var, self.extension_var, self.topic_var, self.date_from_var, self.date_to_var, self.min_size_var, self.max_size_var):
            var.set("")
        self.category_var.set("Any")
        self._search()

    def _search(self) -> None:
        try:
            index = SearchIndex()
            self.rows = index.search(
                query=self.query_var.get(), location=self.location_var.get(),
                category=self.category_var.get(), extension=self.extension_var.get(),
                topic=self.topic_var.get(), date_from=self.date_from_var.get(),
                date_to=self.date_to_var.get(), min_size_mb=self.min_size_var.get(),
                max_size_mb=self.max_size_var.get(), limit=5000,
            )
            index.close()
        except ValueError:
            messagebox.showwarning("Check search filters", "Dates must use YYYY-MM-DD and size filters must be numbers.", parent=self)
            return
        except Exception as error:
            messagebox.showerror("Search failed", str(error), parent=self)
            return
        for child in self.tree.get_children(): self.tree.delete(child)
        self.preview.configure(state="normal"); self.preview.delete("1.0", "end")
        self.preview.insert("1.0", "Select a result to preview its indexed text."); self.preview.configure(state="disabled")
        for i, row in enumerate(self.rows):
            modified = datetime.fromtimestamp(row["modified_ts"]).strftime("%Y-%m-%d %H:%M")
            self.tree.insert("", "end", iid=str(i), values=(
                row["name"], row["category"], row["extension"], _size(row["size_bytes"]),
                modified, row["topic"], row["path"],
            ))
        self.status_var.set(f"Found {len(self.rows):,} result(s). Showing up to 5,000 matching indexed files.")

    def _preview_selected(self, _event=None) -> None:
        row = self._selected()
        if not row:
            return
        body = str(row.get("body", "")).strip()
        preview = body[:3000] if body else "No extracted text is available for this file. The filename and file metadata are still searchable."
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", f"{row['name']}\n{row['path']}\n\n{preview}")
        self.preview.configure(state="disabled")

    def _selected(self) -> dict | None:
        selected = self.tree.selection()
        if not selected: return None
        return self.rows[int(selected[0])]

    def _open(self) -> None:
        row = self._selected()
        if row and Path(row["path"]).is_file(): _open_path(Path(row["path"]))

    def _reveal(self) -> None:
        row = self._selected()
        if row and Path(row["path"]).exists(): _show_in_folder(Path(row["path"]))

    def _start_index(self) -> None:
        if self.busy: return
        source_entries = self.parent_app._selected_source_entries()
        sources = [path for path, _label in source_entries]
        if not sources:
            messagebox.showwarning("Select search locations", "Return to the main window and select one or more drives or folders first.", parent=self)
            return
        categories = list(self.categories)
        extension_filters = self.parent_app.extension_filters
        self._start_worker("index", lambda report, control: build_index(
            sources, categories, extension_filters=extension_filters,
            progress=report, extract_text=True, control=control,
        ))

    def _start_duplicates(self) -> None:
        if self.busy:
            return
        source_entries = self.parent_app._selected_source_entries()
        sources = [path for path, _label in source_entries]
        if not sources:
            messagebox.showwarning(
                "Select search locations",
                "Return to the main window and select one or more drives or folders first. "
                "Duplicate analysis refreshes the local index before comparing files.",
                parent=self,
            )
            return
        categories = list(self.categories)
        extension_filters = self.parent_app.extension_filters

        def index_then_analyze(report, control):
            indexed = build_index(
                sources, categories, extension_filters=extension_filters,
                progress=report, extract_text=True, control=control,
            )
            if indexed.get("cancelled"):
                raise OperationCancelled("Duplicate analysis was cancelled during indexing.")
            result = analyze_duplicates(progress=report, control=control)
            result["index_result"] = indexed
            return result

        self._start_worker("duplicates", index_then_analyze)

    def _start_worker(self, kind: str, work) -> None:
        if self.busy:
            return
        self.busy = True
        self.operation_control = OperationControl()
        self.pause_button.configure(state="normal", text="Pause")
        self.cancel_button.configure(state="normal")
        self.status_var.set("Working…")
        control = self.operation_control

        def run():
            try:
                report = lambda message: self.events.put(("progress", kind, message))
                self.events.put(("done", kind, work(report, control)))
            except OperationCancelled as error:
                self.events.put(("cancelled", kind, str(error)))
            except Exception as error:
                self.events.put(("error", kind, str(error)))
        threading.Thread(target=run, name=f"sdo-search-{kind}", daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                event, kind, payload = self.events.get_nowait()
                if event == "progress":
                    if isinstance(payload, dict):
                        phase = str(payload.get("phase", ""))
                        if phase == "index":
                            checked = int(payload.get("files_checked", 0) or 0)
                            total = int(payload.get("files_indexed", 0) or 0)
                            self.status_var.set(
                                f"Indexing {payload.get('current_root','')}: {checked:,} checked, {total:,} indexed, "
                                f"{int(payload.get('skipped',0) or 0):,} skipped"
                            )
                        elif phase == "duplicates_hash":
                            self.status_var.set(
                                f"Checking duplicates: {int(payload.get('records_checked',0) or 0):,}/"
                                f"{int(payload.get('records_total',0) or 0):,} files hashed"
                            )
                        elif phase == "duplicates_compare":
                            self.status_var.set(
                                f"Comparing document text: {int(payload.get('pairs_checked',0) or 0):,}/"
                                f"{int(payload.get('candidate_pairs',0) or 0):,} candidate pairs"
                            )
                    else:
                        self.status_var.set(str(payload))
                elif event == "error":
                    self.busy = False
                    self.operation_control = None
                    self.pause_button.configure(state="disabled", text="Pause")
                    self.cancel_button.configure(state="disabled")
                    self.status_var.set("Operation stopped.")
                    messagebox.showerror("Smart Drive Organizer", str(payload), parent=self)
                elif event == "cancelled":
                    self.busy = False
                    self.operation_control = None
                    self.pause_button.configure(state="disabled", text="Pause")
                    self.cancel_button.configure(state="disabled")
                    self.status_var.set("Operation cancelled safely; local index and source files were preserved.")
                    messagebox.showinfo("Operation cancelled", str(payload) or "Cancelled at a safe checkpoint.", parent=self)
                elif event == "done":
                    self.busy = False
                    self.operation_control = None
                    self.pause_button.configure(state="disabled", text="Pause")
                    self.cancel_button.configure(state="disabled")
                    if kind == "index":
                        self.status_var.set(
                            f"Index refreshed: {payload['refreshed']:,} changed/new; {payload['total']:,} total; {payload['skipped']:,} skipped."
                        )
                        self._refresh_count()
                        self._search()
                    elif kind == "duplicates":
                        DuplicateReviewDialog(self, payload)
                        self.status_var.set("Duplicate review completed. No files were changed.")
        except queue.Empty:
            pass
        self._after_id = self.after(120, self._poll)
