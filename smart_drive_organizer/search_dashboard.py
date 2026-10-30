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

from .duplicates import analyze_duplicates
from .search_index import SearchIndex, build_index


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
        bg, black, white, red = "#F4F4F5", "#101010", "#FFFFFF", "#D71920"
        self.configure(bg=bg)
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=black, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=bg, foreground=black, font=("Segoe UI", 18, "bold"))
        style.configure("Treeview", rowheight=27, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background=black, foreground=white, font=("Segoe UI", 9, "bold"), padding=7)
        style.configure("Primary.TButton", background=red, foreground=white, font=("Segoe UI", 9, "bold"), padding=9)
        outer = ttk.Frame(self, padding=14); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Review possible duplicates and revisions", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text=f"Checked {result.get('records_checked', 0):,} indexed files and found {result.get('total_groups', 0):,} groups. No files were changed or deleted.", wraplength=940).pack(anchor="w", pady=(5, 12))
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
        self.file_list = tk.Listbox(details, width=52, height=23, font=("Segoe UI", 8), selectbackground=red, selectforeground=white)
        self.file_list.pack(fill="both", expand=True)
        for i, group in enumerate(self.groups):
            sim = "—" if group.get("similarity") is None else f"{group['similarity']:.0%}"
            self.tree.insert("", "end", iid=str(i), values=(group["kind"], group["count"], sim, group["match"]))
        self.tree.bind("<<TreeviewSelect>>", self._select)
        self.file_list.bind("<Double-1>", lambda _e: self._open())
        actions = ttk.Frame(outer); actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Open selected file", command=self._open).pack(side="left")
        ttk.Button(actions, text="Show in folder", command=self._reveal).pack(side="left", padx=6)
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")
        if self.groups:
            self.tree.selection_set("0"); self._select()

    def _select(self, _event=None):
        ids = self.tree.selection()
        self.file_list.delete(0, "end")
        self.active_files = []
        if not ids: return
        group = self.groups[int(ids[0])]
        self.active_files = group.get("files", [])
        for row in self.active_files:
            self.file_list.insert("end", row["path"])

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
        bg, white, black, red, muted = "#F4F4F5", "#FFFFFF", "#101010", "#D71920", "#666666"
        self.configure(bg=bg)
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=black, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=bg, foreground=black, font=("Segoe UI", 22, "bold"))
        style.configure("Hint.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
        style.configure("TEntry", padding=8, fieldbackground=white)
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 7))
        style.configure("Primary.TButton", background=red, foreground=white, font=("Segoe UI", 9, "bold"), padding=(14, 9))
        style.map("Primary.TButton", background=[("active", "#B9151B")])
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 9), background=white, fieldbackground=white)
        style.configure("Treeview.Heading", background=black, foreground=white, font=("Segoe UI", 9, "bold"), padding=7)

        outer = ttk.Frame(self, padding=18); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Search everything you have indexed", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Search filenames and extracted text stored locally on this computer. Use filters to narrow results and open the original file location.", style="Hint.TLabel").pack(anchor="w", pady=(4, 12))

        search_row = ttk.Frame(outer); search_row.pack(fill="x", pady=(0, 10))
        self.query_var = tk.StringVar()
        self.query_entry = ttk.Entry(search_row, textvariable=self.query_var, font=("Segoe UI", 13))
        self.query_entry.pack(side="left", fill="x", expand=True)
        self.query_entry.bind("<Return>", lambda _e: self._search())
        ttk.Button(search_row, text="SEARCH", style="Primary.TButton", command=self._search).pack(side="left", padx=(8, 0))
        ttk.Button(search_row, text="Build / refresh index", command=self._start_index).pack(side="left", padx=(8, 0))

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
        ttk.Button(toolbar, text="Find duplicates & versions", command=self._start_duplicates).pack(side="right")

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
        result_frame.rowconfigure(0, weight=1); result_frame.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _e: self._open())
        actions = ttk.Frame(outer); actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Open file", command=self._open).pack(side="left")
        ttk.Button(actions, text="Show in folder", command=self._reveal).pack(side="left", padx=6)
        self.index_count_var = tk.StringVar(value="Local index")
        ttk.Label(actions, textvariable=self.index_count_var, style="Hint.TLabel").pack(side="right")
        self.after(100, self._poll)
        self.query_entry.focus_set()
        self._refresh_count()

    @staticmethod
    def _field(parent, label: str, variable: tk.StringVar, row: int, col: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row+1, column=col, sticky="ew", padx=5, pady=(0, 5))

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
        for i, row in enumerate(self.rows):
            modified = datetime.fromtimestamp(row["modified_ts"]).strftime("%Y-%m-%d %H:%M")
            self.tree.insert("", "end", iid=str(i), values=(
                row["name"], row["category"], row["extension"], _size(row["size_bytes"]),
                modified, row["topic"], row["path"],
            ))
        self.status_var.set(f"Found {len(self.rows):,} result(s). Showing up to 5,000 matching indexed files.")

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
        self._start_worker("index", lambda report: build_index(
            sources, categories, extension_filters=extension_filters,
            progress=report, extract_text=True,
        ))

    def _start_duplicates(self) -> None:
        if self.busy: return
        self._start_worker("duplicates", lambda report: analyze_duplicates(progress=report))

    def _start_worker(self, kind: str, work) -> None:
        self.busy = True
        self.status_var.set("Working…")
        def run():
            try: self.events.put(("done", kind, work(lambda message: self.events.put(("progress", "message", message)))))
            except Exception as error: self.events.put(("error", kind, str(error)))
        threading.Thread(target=run, name=f"sdo-search-{kind}", daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                event, kind, payload = self.events.get_nowait()
                if event == "progress":
                    self.status_var.set(str(payload))
                elif event == "error":
                    self.busy = False
                    self.status_var.set("Operation stopped.")
                    messagebox.showerror("Smart Drive Organizer", str(payload), parent=self)
                elif event == "done":
                    self.busy = False
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
        self.after(120, self._poll)
