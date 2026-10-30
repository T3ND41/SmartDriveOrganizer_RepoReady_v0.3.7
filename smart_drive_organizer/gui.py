from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from . import __version__
from .classifier import load_custom_rules, save_custom_rules, load_topic_rules, save_topic_rules
from .automation import (
    is_service_running, load_settings, mark_undo_restored_sources, read_service_status, settings_path, topic_rules_path,
    start_background_monitor, stop_background_monitor,
)
from .automation_ui import AutomationSettingsDialog
from .drives import discover_drives
from .models import ScanPlan
from .operations import latest_movable_journal, run_plan, undo_move_journal
from .scanner import scan_directories
from .topic_rules_ui import TopicRulesDialog
from .github_publish_ui import GitHubPublishDialog

CATEGORIES = ["Documents", "Images", "Videos", "Audio", "Archives", "Code", "Applications", "Fonts", "3D Models", "Others"]
MAX_PREVIEW_ROWS = 1200


def app_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / "SmartDriveOrganizer"
    path.mkdir(parents=True, exist_ok=True)
    return path


def rules_file() -> Path:
    path = app_data_dir() / "keyword_rules.json"
    if not path.exists():
        bundled = Path(__file__).resolve().parent.parent / "config" / "keyword_rules.json"
        if bundled.exists():
            path.write_text(bundled.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            path.write_text("[]", encoding="utf-8")
    return path


def topic_rules_file() -> Path:
    return topic_rules_path()


class OrganizerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Smart Drive Organizer {__version__}")
        self.geometry("1180x850")
        self.minsize(980, 700)
        self.configure(bg="#f3f5f8")

        self.source_entries: list[tuple[Path, str]] = []
        self.output_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="copy")
        self.recursive_var = tk.BooleanVar(value=True)
        self.content_var = tk.BooleanVar(value=True)
        self.category_vars = {name: tk.BooleanVar(value=(name == "Documents")) for name in CATEGORIES}
        saved_automation = load_settings()
        self.topic_filter_var = tk.BooleanVar(value=saved_automation.topic_filter_enabled)
        self.topic_rules = load_topic_rules(topic_rules_file())
        self.topic_vars: dict[str, tk.BooleanVar] = {}
        for name in self._available_topic_names():
            self.topic_vars[name] = tk.BooleanVar(value=(name in saved_automation.selected_topics))
        self.status_var = tk.StringVar(value="Select one or more drives or folders, then choose an output folder.")
        self.summary_var = tk.StringVar(value="No scan yet.")
        self.progress_var = tk.DoubleVar(value=0)
        self.automation_status_var = tk.StringVar(value="Automatic monitor: not running")

        self.plan: Optional[ScanPlan] = None
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.job_kind: Optional[str] = None
        self._build_ui()
        self.after(120, self._poll_events)

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#f3f5f8")
        style.configure("Card.TLabelframe", background="#ffffff", borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", background="#ffffff", foreground="#1b2b43", font=("Segoe UI", 10, "bold"))
        style.configure("TLabel", background="#f3f5f8", foreground="#26364a", font=("Segoe UI", 9))
        style.configure("Title.TLabel", background="#f3f5f8", foreground="#172a43", font=("Segoe UI", 19, "bold"))
        style.configure("Sub.TLabel", background="#f3f5f8", foreground="#5b6b7f", font=("Segoe UI", 9))
        style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(13, 8))
        style.configure("Treeview", rowheight=25, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Smart Drive Organizer", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Collect related files by meaning, then separate each group by file extension.", style="Sub.TLabel").pack(anchor="w", pady=(2, 12))

        locations = ttk.LabelFrame(outer, text="1. Choose source drives and destination", style="Card.TLabelframe", padding=12)
        locations.pack(fill="x", pady=(0, 10))
        locations.columnconfigure(1, weight=1)
        ttk.Label(locations, text="Source drives / folders").grid(row=0, column=0, sticky="nw", padx=(0, 10), pady=5)
        source_frame = ttk.Frame(locations)
        source_frame.grid(row=0, column=1, sticky="nsew", pady=5)
        self.source_listbox = tk.Listbox(
            source_frame, selectmode=tk.EXTENDED, exportselection=False, height=4,
            font=("Segoe UI", 9), activestyle="dotbox", relief="solid", borderwidth=1,
        )
        self.source_listbox.pack(side="left", fill="both", expand=True)
        source_scroll = ttk.Scrollbar(source_frame, orient="vertical", command=self.source_listbox.yview)
        source_scroll.pack(side="right", fill="y")
        self.source_listbox.configure(yscrollcommand=source_scroll.set)
        source_buttons = ttk.Frame(locations)
        source_buttons.grid(row=0, column=2, sticky="ns", padx=(8, 0), pady=5)
        ttk.Button(source_buttons, text="Refresh drives", command=self._refresh_drives).pack(fill="x", pady=(0, 4))
        ttk.Button(source_buttons, text="Select all", command=self._select_all_sources).pack(fill="x", pady=2)
        ttk.Button(source_buttons, text="Clear", command=self._clear_sources).pack(fill="x", pady=2)
        ttk.Button(source_buttons, text="Add folder…", command=self._add_source_folder).pack(fill="x", pady=(4, 0))
        ttk.Label(locations, text="Output / destination folder").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(locations, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Button(locations, text="Browse…", command=self._browse_output).grid(row=1, column=2, padx=(8, 0), pady=5)
        ttk.Label(
            locations,
            text="Choose multiple drives (for example C: and D:). Network drives are listed but not preselected. You may use a destination folder inside a selected drive: that output folder is excluded from scanning.",
            style="Sub.TLabel", wraplength=980,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        options = ttk.Frame(outer)
        options.pack(fill="x", pady=(0, 10))
        filetypes = ttk.LabelFrame(options, text="2. File types to organize", style="Card.TLabelframe", padding=10)
        filetypes.pack(side="left", fill="both", expand=True, padx=(0, 8))
        for index, category in enumerate(CATEGORIES):
            row, col = divmod(index, 5)
            ttk.Checkbutton(filetypes, text=category, variable=self.category_vars[category]).grid(row=row, column=col, sticky="w", padx=(0, 12), pady=3)
        type_buttons = ttk.Frame(filetypes)
        type_buttons.grid(row=2, column=0, columnspan=5, sticky="w", pady=(5, 0))
        ttk.Button(type_buttons, text="Select all", command=lambda: self._select_categories(True)).pack(side="left")
        ttk.Button(type_buttons, text="Clear", command=lambda: self._select_categories(False)).pack(side="left", padx=(6, 0))

        action = ttk.LabelFrame(options, text="3. How to organize", style="Card.TLabelframe", padding=10)
        action.pack(side="left", fill="y", padx=(8, 0))
        ttk.Radiobutton(action, text="Copy files (safest first run)", variable=self.mode_var, value="copy").pack(anchor="w", pady=3)
        ttk.Radiobutton(action, text="Move files", variable=self.mode_var, value="move").pack(anchor="w", pady=3)
        ttk.Separator(action).pack(fill="x", pady=7)
        ttk.Checkbutton(action, text="Include subfolders", variable=self.recursive_var).pack(anchor="w", pady=3)
        ttk.Checkbutton(action, text="Read document text where possible", variable=self.content_var).pack(anchor="w", pady=3)
        ttk.Button(action, text="Add keyword rule…", command=self._add_rule).pack(anchor="w", pady=(8, 0))

        selective = ttk.LabelFrame(outer, text="Optional: organize only the topic groups you select", style="Card.TLabelframe", padding=9)
        selective.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            selective,
            text="Only organize files matching the selected topic groups; leave all other files untouched",
            variable=self.topic_filter_var,
        ).pack(anchor="w")
        self.topic_options_frame = ttk.Frame(selective)
        self.topic_options_frame.pack(anchor="w", pady=(4, 0), fill="x")
        self._refresh_topic_options()
        ttk.Button(selective, text="Add / manage my own topic groups…", command=self._manage_topic_groups).pack(anchor="w", pady=(6, 0))
        ttk.Label(
            selective,
            text="Create a folder label and enter matching words or phrases. Filename matching works for all selected file types; supported document text can also be searched when enabled.",
            style="Sub.TLabel", wraplength=980,
        ).pack(anchor="w", pady=(5, 0))

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 8))
        self.scan_button = ttk.Button(controls, text="Scan and preview", style="Primary.TButton", command=self._scan)
        self.scan_button.pack(side="left")
        self.apply_button = ttk.Button(controls, text="Apply organization", style="Primary.TButton", command=self._apply, state="disabled")
        self.apply_button.pack(side="left", padx=8)
        self.undo_button = ttk.Button(controls, text="Undo last move", command=self._undo)
        self.undo_button.pack(side="left")
        ttk.Button(controls, text="Undo last automatic move", command=self._undo_auto_move).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Automation settings…", command=self._open_automation_settings).pack(side="left", padx=(8, 0))
        self.automation_button = ttk.Button(controls, text="Start monitor", command=self._toggle_automation)
        self.automation_button.pack(side="left", padx=8)
        ttk.Button(controls, text="Open output folder", command=self._open_output).pack(side="right")
        ttk.Button(controls, text="Activity log", command=self._open_activity_log).pack(side="right", padx=(0, 8))
        ttk.Button(controls, text="Publish rules to GitHub…", command=self._open_github_publisher).pack(side="right", padx=(0, 8))

        preview = ttk.LabelFrame(outer, text="4. Preview — nothing changes until you apply", style="Card.TLabelframe", padding=8)
        preview.pack(fill="both", expand=True)
        columns = ("file", "category", "group", "extension", "confidence", "destination")
        self.table = ttk.Treeview(preview, columns=columns, show="headings", height=14)
        headings = {"file": "File", "category": "Type", "group": "Keyword group", "extension": "Extension", "confidence": "Match", "destination": "Planned destination"}
        widths = {"file": 170, "category": 95, "group": 160, "extension": 82, "confidence": 75, "destination": 420}
        for column in columns:
            self.table.heading(column, text=headings[column])
            self.table.column(column, width=widths[column], minwidth=60, stretch=(column == "destination"))
        yscroll = ttk.Scrollbar(preview, orient="vertical", command=self.table.yview)
        xscroll = ttk.Scrollbar(preview, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        preview.rowconfigure(0, weight=1)
        preview.columnconfigure(0, weight=1)

        ttk.Label(outer, textvariable=self.summary_var).pack(anchor="w", pady=(8, 2))
        self.progress = ttk.Progressbar(outer, variable=self.progress_var, maximum=100, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 5))
        ttk.Label(outer, textvariable=self.status_var, style="Sub.TLabel").pack(anchor="w")
        ttk.Label(outer, textvariable=self.automation_status_var, style="Sub.TLabel").pack(anchor="w", pady=(2, 0))
        self._refresh_drives(select_defaults=True)
        self.after(1000, self._refresh_automation_status)

    def _open_automation_settings(self) -> None:
        AutomationSettingsDialog(self, self._refresh_automation_status)

    def _open_github_publisher(self) -> None:
        GitHubPublishDialog(self, topic_rules_file())

    def _toggle_automation(self) -> None:
        try:
            if is_service_running():
                stop_background_monitor()
                self.automation_status_var.set("Automatic monitor: stopping…")
            else:
                pid = start_background_monitor()
                self.automation_status_var.set(f"Automatic monitor: starting (PID {pid})…")
        except Exception as error:
            messagebox.showerror("Automatic monitoring", str(error))
        self.after(1000, self._refresh_automation_status)

    def _refresh_automation_status(self) -> None:
        running = is_service_running()
        self.automation_button.configure(text="Stop monitor" if running else "Start monitor")
        status = read_service_status()
        if running:
            message = str(status.get("last_message", "Running in the background."))
            self.automation_status_var.set(
                f"Automatic monitor: RUNNING — {message} | Organized: {status.get('files_organized', 0)}"
            )
        else:
            last_message = str(status.get("last_message", ""))
            if last_message.startswith("Monitor stopped:"):
                self.automation_status_var.set(f"Automatic monitor: stopped — {last_message}")
            else:
                self.automation_status_var.set("Automatic monitor: not running. Configure folders in Automation settings.")
        self.after(3000, self._refresh_automation_status)

    def _refresh_drives(self, select_defaults: bool = False) -> None:
        previous = {os.path.normcase(str(path.resolve())) for path, _ in self._selected_source_entries()}
        try:
            drives = discover_drives()
        except Exception as error:
            drives = []
            self.status_var.set(f"Could not automatically detect drives: {error}")

        # Keep manually added folders when the drive list is refreshed.
        manual = [(path, label) for path, label in self.source_entries if label.startswith("[Folder]")]
        drive_entries = [(drive.root, drive.display_name) for drive in drives]
        self.source_entries = drive_entries + manual
        self.source_listbox.delete(0, "end")
        selected_indices = []
        for index, (path, label) in enumerate(self.source_entries):
            self.source_listbox.insert("end", label)
            key = os.path.normcase(str(path.resolve()))
            drive = next((item for item in drives if item.root == path), None)
            if key in previous or (select_defaults and drive is not None and drive.default_selected):
                selected_indices.append(index)
        for index in selected_indices:
            self.source_listbox.selection_set(index)
        if not drives and not manual:
            self.status_var.set("No drives were detected automatically. Use Add folder to select a source folder.")
        elif select_defaults:
            self.status_var.set(f"Detected {len(drives)} mounted drive(s). Local fixed/removable drives are preselected; choose or clear as needed.")

    def _selected_source_entries(self) -> list[tuple[Path, str]]:
        if not hasattr(self, "source_listbox"):
            return []
        return [self.source_entries[index] for index in self.source_listbox.curselection()]

    def _select_all_sources(self) -> None:
        self.source_listbox.selection_set(0, "end")

    def _clear_sources(self) -> None:
        self.source_listbox.selection_clear(0, "end")

    def _add_source_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Add another source folder")
        if not chosen:
            return
        path = Path(chosen).expanduser().resolve()
        key = os.path.normcase(str(path))
        for index, (existing, _) in enumerate(self.source_entries):
            if os.path.normcase(str(existing.resolve())) == key:
                self.source_listbox.selection_set(index)
                self.source_listbox.see(index)
                return
        label = f"[Folder] {path}"
        self.source_entries.append((path, label))
        self.source_listbox.insert("end", label)
        index = len(self.source_entries) - 1
        self.source_listbox.selection_set(index)
        self.source_listbox.see(index)

    def _browse_output(self) -> None:
        chosen = filedialog.askdirectory(title="Select the destination folder for organized files")
        if chosen:
            self.output_var.set(chosen)

    def _select_categories(self, enabled: bool) -> None:
        for variable in self.category_vars.values():
            variable.set(enabled)

    def _selected_categories(self) -> list[str]:
        return [name for name, variable in self.category_vars.items() if variable.get()]

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.scan_button.configure(state=state)
        self.apply_button.configure(state="disabled" if busy or not self.plan or not self.plan.files else "normal")
        if busy:
            self.progress.start(10)
            if message:
                self.status_var.set(message)
        else:
            self.progress.stop()
            self.progress_var.set(0)

    def _start_job(self, kind: str, worker: Callable[[Callable[[str], None]], object]) -> None:
        if self.busy:
            return
        self.job_kind = kind
        self._set_busy(True, "Working…")

        def run() -> None:
            try:
                result = worker(lambda message: self.events.put(("progress", message)))
                self.events.put(("done", result))
            except Exception as error:
                self.events.put(("error", str(error)))

        threading.Thread(target=run, name=f"sdo-{kind}", daemon=True).start()

    def _poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "progress":
                    self.status_var.set(str(payload))
                elif event == "error":
                    self._set_busy(False)
                    self.status_var.set("The operation stopped. No unapproved changes were made.")
                    messagebox.showerror("Smart Drive Organizer", str(payload))
                elif event == "done":
                    self._set_busy(False)
                    self._job_finished(payload)
        except queue.Empty:
            pass
        self.after(120, self._poll_events)

    def _job_finished(self, result: object) -> None:
        if self.job_kind == "scan":
            assert isinstance(result, ScanPlan)
            self.plan = result
            self._show_plan(result)
        elif self.job_kind == "apply":
            data = result
            self.plan = None
            self.apply_button.configure(state="disabled")
            journal = data["journal"]
            mode = journal["mode"]
            self.status_var.set(f"Run {journal['run_id']} finished. Audit log: {data['journal_path']}")
            messagebox.showinfo(
                "Organization complete",
                f"{data['succeeded']:,} file(s) processed; {data['failed']:,} failed.\n\n"
                + ("Original files were left in place (copy mode)." if mode == "copy" else "Files were relocated only after the safe move step succeeded.")
                + (f"\nFiles with an original still in place: {data.get('source_kept', 0):,}. Check the run journal." if data.get("source_kept", 0) else "")
                + f"\n\nAudit log:\n{data['journal_path']}"
            )
        elif self.job_kind == "undo":
            self.status_var.set(f"Undo finished: {result['restored']} restored; {result['skipped']} skipped.")
            messagebox.showinfo("Undo finished", f"Restored: {result['restored']}\nSkipped: {result['skipped']}\n\n" + "\n".join(result.get("errors", [])[:8]))
        self.job_kind = None

    def _show_plan(self, plan: ScanPlan) -> None:
        for row in self.table.get_children():
            self.table.delete(row)
        for item in plan.files[:MAX_PREVIEW_ROWS]:
            relative = item.destination
            try:
                relative = item.destination.relative_to(plan.output_root)
            except ValueError:
                pass
            self.table.insert("", "end", values=(
                item.source.name,
                item.category,
                item.topic,
                item.extension_folder,
                f"{item.confidence:.0%}",
                str(relative),
            ))
        extra = max(0, len(plan.files) - MAX_PREVIEW_ROWS)
        size_gb = plan.total_bytes / (1024 ** 3)
        self.summary_var.set(
            f"Preview: {len(plan.files):,} file(s), {size_gb:.2f} GB total; "
            f"{plan.scanned_count:,} files checked across {len(plan.source_roots):,} source(s); "
            f"{plan.skipped_count:,} skipped. "
            + (f"Showing first {MAX_PREVIEW_ROWS:,} rows." if extra else "")
        )
        self.apply_button.configure(state="normal" if plan.files else "disabled")
        if plan.warnings:
            self.status_var.set(f"Scan completed with {len(plan.warnings)} warning(s). First: {plan.warnings[0]}")
        else:
            self.status_var.set("Scan complete. Review the planned folders, then choose Apply organization.")
        if not plan.files:
            messagebox.showwarning("No matching files", "No files matched the selected categories. Try selecting more file types or another source folder.")

    def _scan(self) -> None:
        selected_sources = self._selected_source_entries()
        output_text = self.output_var.get().strip()
        selected = self._selected_categories()
        if not selected_sources or not output_text:
            messagebox.showwarning("Missing location", "Select at least one source drive/folder and choose an output destination folder.")
            return
        if not selected:
            messagebox.showwarning("No file types", "Select at least one file category.")
            return
        sources = [path for path, _ in selected_sources]
        output = Path(output_text).expanduser()
        rules = load_custom_rules(rules_file())
        self.plan = None
        self.apply_button.configure(state="disabled")
        for row in self.table.get_children():
            self.table.delete(row)
        self.summary_var.set(f"Scanning {len(sources)} source drive(s)/folder(s)…")
        selected_topics = [name for name, variable in self.topic_vars.items() if variable.get()]
        if self.topic_filter_var.get() and not selected_topics:
            messagebox.showwarning("No topics selected", "Select at least one topic group, or create your own using Add / manage my own topic groups.")
            return
        topic_rules = load_topic_rules(topic_rules_file())
        self._start_job("scan", lambda progress: scan_directories(
            sources, output, selected,
            recursive=self.recursive_var.get(),
            read_contents=self.content_var.get(),
            custom_rules=rules,
            progress=progress,
            topic_filter_enabled=self.topic_filter_var.get(),
            selected_topics=selected_topics,
            topic_rules=topic_rules,
        ))

    def _apply(self) -> None:
        if not self.plan or not self.plan.files:
            return
        mode = self.mode_var.get()
        warning = (
            f"You are about to {mode.upper()} {len(self.plan.files):,} file(s) collected from "
            f"{len(self.plan.source_roots):,} source drive(s)/folder(s) to:\n\n{self.plan.output_root}\n\n"
            + ("The originals will remain in their current locations." if mode == "copy" else "MOVE relocates the original files. Cross-drive moves are checksum-verified before the source copy is removed.")
            + "\n\nNothing is overwritten. Continue?"
        )
        if not messagebox.askyesno("Confirm organization", warning, icon="warning"):
            return
        plan = self.plan
        self._start_job("apply", lambda progress: run_plan(plan, mode, progress))

    def _undo(self) -> None:
        output_text = self.output_var.get().strip()
        if not output_text:
            messagebox.showwarning("Output folder required", "Enter the output folder used for the move run.")
            return
        journal = latest_movable_journal(Path(output_text).expanduser().resolve())
        if journal is None:
            messagebox.showinfo("No move to undo", "No completed or partially completed move run was found in this output folder.")
            return
        if not messagebox.askyesno("Undo last move", f"Restore files from this move run to their original paths?\n\n{journal}\n\nFiles will not overwrite anything already at the original locations.", icon="warning"):
            return
        self._start_job("undo", lambda progress: self._undo_and_sync(journal, progress))

    def _undo_auto_move(self) -> None:
        config = load_settings()
        output_text = config.output_folder.strip()
        if not output_text:
            messagebox.showwarning("Automation destination required", "Set the output destination in Automation settings first.")
            return
        output = Path(output_text).expanduser().resolve()
        journal = latest_movable_journal(output, origin="automatic")
        if journal is None:
            messagebox.showinfo("No automatic move to undo", "No automatic Move journal was found in the configured output folder.")
            return
        if not messagebox.askyesno(
            "Undo last automatic move",
            f"Restore files from the latest Move journal to their original paths?\n\n{journal}\n\nExisting files will never be overwritten.",
            icon="warning",
        ):
            return
        self._start_job("undo", lambda progress: self._undo_and_sync(journal, progress))

    def _undo_and_sync(self, journal: Path, progress: Callable[[str], None]) -> object:
        result = undo_move_journal(journal, progress)
        try:
            mark_undo_restored_sources(journal)
        except Exception:
            # The move journal is still the source of truth if the watcher index cannot be refreshed.
            pass
        return result

    def _open_activity_log(self) -> None:
        from .automation import app_data_dir
        path = app_data_dir() / "automation_activity.jsonl"
        if not path.exists():
            messagebox.showinfo("No activity yet", "The background organizer has not recorded any file actions yet.")
            return
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                webbrowser.open(path.as_uri())
        except Exception as error:
            messagebox.showerror("Could not open activity log", str(error))

    def _open_output(self) -> None:
        value = self.output_var.get().strip()
        if not value:
            return
        path = Path(value).expanduser()
        if not path.exists():
            messagebox.showinfo("Output not created", "The output folder will be created when you apply a plan.")
            return
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                webbrowser.open(path.as_uri())
        except Exception as error:
            messagebox.showerror("Could not open folder", str(error))

    def _available_topic_names(self) -> list[str]:
        names = ["Statements", "Requisitions", "Quotations"]
        for rule in getattr(self, "topic_rules", []):
            name = str(rule.get("name", "")).strip()
            if name and name.casefold() not in {item.casefold() for item in names}:
                names.append(name)
        return names

    def _refresh_topic_options(self) -> None:
        previous = {name: variable.get() for name, variable in self.topic_vars.items()}
        for child in self.topic_options_frame.winfo_children():
            child.destroy()
        names = self._available_topic_names()
        self.topic_vars = {
            name: tk.BooleanVar(value=previous.get(name, name in load_settings().selected_topics))
            for name in names
        }
        for index, name in enumerate(names):
            row, col = divmod(index, 4)
            ttk.Checkbutton(self.topic_options_frame, text=name, variable=self.topic_vars[name]).grid(
                row=row, column=col, sticky="w", padx=(0, 18), pady=2
            )

    def _manage_topic_groups(self) -> None:
        current = load_topic_rules(topic_rules_file())

        def saved(rules: list[dict]) -> None:
            save_topic_rules(topic_rules_file(), rules)
            self.topic_rules = rules
            self._refresh_topic_options()

        dialog = TopicRulesDialog(self, current, saved)
        self.wait_window(dialog)

    def _add_rule(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Add keyword group")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        name_var = tk.StringVar()
        words_var = tk.StringVar()
        category_var = tk.StringVar(value="Documents")
        ttk.Label(frame, text="Folder name to create").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=name_var, width=42).grid(row=0, column=1, pady=5)
        ttk.Label(frame, text="Words / phrases (comma-separated)").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=words_var, width=42).grid(row=1, column=1, pady=5)
        ttk.Label(frame, text="Apply to file type").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Combobox(frame, textvariable=category_var, values=["Any"] + CATEGORIES, state="readonly", width=39).grid(row=2, column=1, pady=5)
        ttk.Label(frame, text="Example: 'monthly statement, bank statement' → 'Monthly Statements'", wraplength=430).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 12))

        def save() -> None:
            label = name_var.get().strip()
            words = [word.strip() for word in words_var.get().split(",") if word.strip()]
            if not label or not words:
                messagebox.showwarning("Missing details", "Enter a folder name and at least one keyword.", parent=dialog)
                return
            path = rules_file()
            existing = load_custom_rules(path)
            existing.append({"name": label, "keywords": words, "category": category_var.get()})
            save_custom_rules(path, existing)
            messagebox.showinfo("Rule saved", "Your keyword rule has been saved. Run Scan and preview again to use it.", parent=dialog)
            dialog.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="Save rule", command=save).pack(side="right", padx=6)


def launch() -> None:
    app = OrganizerApp()
    app.mainloop()
