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
from .discovery_ui import DiscoveryReviewDialog
from .operations import latest_movable_journal, run_plan, undo_move_journal
from .scanner import scan_directories
from .topic_rules_ui import TopicRulesDialog
from .github_publish_ui import GitHubPublishDialog
from .file_types import FileTypeSelectionDialog, extension_filter_summary, load_extension_filters, save_extension_filters
from .learning import record_discovery_decisions, record_filing_correction, memory_summary
from .search_dashboard import SearchDashboardDialog
from .memory_ui import LearningMemoryDialog
from .search_index import sync_journal_actions

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
        self.output_var = tk.StringVar(value=str(Path.home() / "Documents" / "Smart Drive Organizer" / "Organized Files"))
        self.mode_var = tk.StringVar(value="copy")
        self.recursive_var = tk.BooleanVar(value=True)
        self.content_var = tk.BooleanVar(value=True)
        self.category_vars = {name: tk.BooleanVar(value=True) for name in CATEGORIES}
        self.extension_filters = load_extension_filters()
        self.file_format_summary_var = tk.StringVar(value=extension_filter_summary(CATEGORIES, self.extension_filters))
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
        bg, white, black, red, muted, border = "#F4F4F5", "#FFFFFF", "#101010", "#D71920", "#737373", "#E4E4E7"
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("TFrame", background=bg)
        style.configure("Page.TFrame", background=bg)
        style.configure("Card.TFrame", background=white)
        style.configure("TLabel", background=bg, foreground=black, font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=white, foreground=black, font=("Segoe UI", 9))
        style.configure("Muted.TLabel", background=white, foreground=muted, font=("Segoe UI", 9))
        style.configure("PageTitle.TLabel", background=bg, foreground=black, font=("Segoe UI", 22, "bold"))
        style.configure("PageSub.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
        style.configure("Card.TLabelframe", background=white, borderwidth=1, relief="solid", bordercolor=border, lightcolor=border, darkcolor=border)
        style.configure("Card.TLabelframe.Label", background=white, foreground=black, font=("Segoe UI", 10, "bold"))
        style.configure("Card.TCheckbutton", background=white, foreground=black, font=("Segoe UI", 9))
        style.map("Card.TCheckbutton", background=[("active", white)])
        style.configure("Card.TRadiobutton", background=white, foreground=black, font=("Segoe UI", 9))
        style.map("Card.TRadiobutton", background=[("active", white)])
        style.configure("TEntry", padding=7, fieldbackground=white, foreground=black)
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 7), background=white, foreground=black)
        style.map("TButton", background=[("active", "#F1F1F1"), ("disabled", "#E5E5E5")])
        style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(16, 10), background=red, foreground=white)
        style.map("Primary.TButton", background=[("active", "#B9151B"), ("disabled", "#E7A1A4")], foreground=[("disabled", white)])
        style.configure("Dark.TButton", font=("Segoe UI", 9, "bold"), padding=(13, 9), background=black, foreground=white)
        style.map("Dark.TButton", background=[("active", "#333333"), ("disabled", "#777777")])
        style.configure("Secondary.TButton", font=("Segoe UI", 9), padding=(10, 7), background="#F4F4F5", foreground=black)
        style.map("Secondary.TButton", background=[("active", "#E4E4E7")])
        style.configure("Treeview", rowheight=29, font=("Segoe UI", 9), background=white, fieldbackground=white, foreground=black)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background=black, foreground=white, padding=(8, 8), relief="flat")
        style.map("Treeview.Heading", background=[("active", red)])
        style.configure("Red.Horizontal.TProgressbar", troughcolor="#E5E5E5", background=red, bordercolor="#E5E5E5", lightcolor=red, darkcolor=red)
        self.configure(bg=bg)

        shell = tk.Frame(self, bg=bg)
        shell.pack(fill="both", expand=True)
        sidebar = tk.Frame(shell, bg=black, width=218)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        logo_path = Path(__file__).resolve().parent / "assets" / "brand_mark.png"
        try:
            self.brand_photo = tk.PhotoImage(file=str(logo_path))
            self.iconphoto(True, self.brand_photo)
            tk.Label(sidebar, image=self.brand_photo, bg=black, borderwidth=0).pack(anchor="w", padx=20, pady=(22, 10))
        except (tk.TclError, OSError):
            tk.Frame(sidebar, bg=red, width=52, height=5).pack(anchor="w", padx=20, pady=(34, 28))
        tk.Label(sidebar, text="SMART DRIVE", bg=black, fg=white, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20)
        tk.Label(sidebar, text="ORGANIZER", bg=black, fg="#F87171", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(0, 22))
        tk.Frame(sidebar, bg=red, height=3).pack(fill="x", padx=20, pady=(0, 20))
        tk.Label(sidebar, text="WORKSPACE", bg=black, fg="#A3A3A3", font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=20, pady=(0, 8))

        def nav_button(label: str, command: Callable[[], None], accent: bool = False) -> None:
            tk.Button(sidebar, text=label, command=command, anchor="w", padx=20, pady=11, relief="flat",
                borderwidth=0, cursor="hand2", bg=red if accent else black, fg=white,
                activebackground="#B9151B" if accent else "#262626", activeforeground=white,
                font=("Segoe UI", 9, "bold" if accent else "normal"), highlightthickness=0).pack(fill="x", padx=10, pady=2)

        nav_button("Overview", lambda: self._scroll_to_section("overview"))
        nav_button("Locations", lambda: self._scroll_to_section("locations"))
        nav_button("File formats", lambda: self._scroll_to_section("filetypes"))
        nav_button("Topic groups & rules", lambda: self._scroll_to_section("selective"))
        nav_button("Search all files", self._open_search_dashboard, accent=True)
        nav_button("Learning memory", self._open_learning_memory)
        nav_button("Automation settings", self._open_automation_settings)
        nav_button("Activity log", self._open_activity_log)
        nav_button("GitHub publishing", self._open_github_publisher)
        tk.Frame(sidebar, bg="#404040", height=1).pack(fill="x", padx=18, pady=(22, 14))
        tk.Label(sidebar, text="PRIVATE BY DESIGN", bg=black, fg=white, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=20)
        tk.Label(sidebar, text="Your files stay on this computer. Nothing changes until you review and confirm.",
            bg=black, fg="#A3A3A3", justify="left", wraplength=172, font=("Segoe UI", 8)).pack(anchor="w", padx=20, pady=(6, 12))
        tk.Label(sidebar, text=f"VERSION {__version__}", bg=black, fg="#737373", font=("Segoe UI", 8)).pack(side="bottom", anchor="w", padx=20, pady=18)

        main = tk.Frame(shell, bg=bg)
        main.pack(side="left", fill="both", expand=True)
        topbar = tk.Frame(main, bg=white, height=72)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        top_left = tk.Frame(topbar, bg=white)
        top_left.pack(side="left", fill="y", padx=24)
        tk.Label(top_left, text="Smart Drive Organizer", bg=white, fg=black, font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(15, 0))
        tk.Label(top_left, text="A safer, clearer way to organize your files", bg=white, fg=muted, font=("Segoe UI", 8)).pack(anchor="w", pady=(1, 0))
        tk.Label(topbar, text="●  LOCAL-FIRST", bg="#FEE2E2", fg=red, font=("Segoe UI", 8, "bold"), padx=10, pady=7).pack(side="right", padx=24, pady=17)
        tk.Frame(main, bg=red, height=3).pack(fill="x")

        scroll_area = tk.Frame(main, bg=bg)
        scroll_area.pack(fill="both", expand=True)
        self.content_canvas = tk.Canvas(scroll_area, bg=bg, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(scroll_area, orient="vertical", command=self.content_canvas.yview)
        self.content_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.content_canvas.pack(side="left", fill="both", expand=True)
        content = ttk.Frame(self.content_canvas, style="Page.TFrame", padding=(24, 22, 24, 26))
        self.content_frame = content
        canvas_window = self.content_canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _event: self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all")))
        self.content_canvas.bind("<Configure>", lambda event: self.content_canvas.itemconfigure(canvas_window, width=event.width))
        self.content_canvas.bind("<Enter>", lambda _event: self.content_canvas.bind_all("<MouseWheel>", lambda event: self.content_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")))
        self.content_canvas.bind("<Leave>", lambda _event: self.content_canvas.unbind_all("<MouseWheel>"))
        self._scroll_targets = {"overview": content}

        intro = ttk.Frame(content, style="Page.TFrame")
        intro.pack(fill="x", pady=(0, 16))
        ttk.Label(intro, text="Organize your drives", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(intro, text="Search selected drives, discover recurring file patterns, review the proposed groups, and organize only after approval.", style="PageSub.TLabel").pack(anchor="w", pady=(4, 0))

        locations = ttk.LabelFrame(content, text="01   SOURCE LOCATIONS", style="Card.TLabelframe", padding=14)
        locations.pack(fill="x", pady=(0, 12))
        self._scroll_targets["locations"] = locations
        locations.columnconfigure(1, weight=1)
        ttk.Label(locations, text="Source drives / folders", style="Card.TLabel").grid(row=0, column=0, sticky="nw", padx=(0, 12), pady=5)
        source_frame = ttk.Frame(locations, style="Card.TFrame")
        source_frame.grid(row=0, column=1, sticky="nsew", pady=4)
        self.source_listbox = tk.Listbox(source_frame, selectmode=tk.EXTENDED, exportselection=False, height=4,
            font=("Segoe UI", 9), activestyle="dotbox", relief="flat", borderwidth=0, bg="#FAFAFA", fg=black,
            selectbackground=red, selectforeground=white, highlightthickness=1, highlightbackground=border)
        self.source_listbox.pack(side="left", fill="both", expand=True)
        source_scroll = ttk.Scrollbar(source_frame, orient="vertical", command=self.source_listbox.yview)
        source_scroll.pack(side="right", fill="y")
        self.source_listbox.configure(yscrollcommand=source_scroll.set)
        source_buttons = ttk.Frame(locations, style="Card.TFrame")
        source_buttons.grid(row=0, column=2, sticky="ns", padx=(10, 0), pady=4)
        ttk.Button(source_buttons, text="Refresh drives", style="Secondary.TButton", command=self._refresh_drives).pack(fill="x", pady=(0, 4))
        ttk.Button(source_buttons, text="Select all", style="Secondary.TButton", command=self._select_all_sources).pack(fill="x", pady=2)
        ttk.Button(source_buttons, text="Clear", style="Secondary.TButton", command=self._clear_sources).pack(fill="x", pady=2)
        ttk.Button(source_buttons, text="Add folder…", style="Secondary.TButton", command=self._add_source_folder).pack(fill="x", pady=(4, 0))
        ttk.Label(locations, text="Output / destination folder", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=8)
        ttk.Entry(locations, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=8)
        ttk.Button(locations, text="Browse…", style="Secondary.TButton", command=self._browse_output).grid(row=1, column=2, padx=(10, 0), pady=8)
        ttk.Label(locations, text="Deep search is read-only. Windows, Program Files, ProgramData, AppData, recovery folders, recycle bins, system files, project/dependency folders and linked folders are skipped to protect the operating system and installed applications. Network drives are opt-in.",
            style="Muted.TLabel", wraplength=900).grid(row=2, column=0, columnspan=3, sticky="w", pady=(5, 0))

        options = ttk.Frame(content, style="Page.TFrame")
        options.pack(fill="x", pady=(0, 12))
        options.columnconfigure(0, weight=3)
        options.columnconfigure(1, weight=2)
        filetypes = ttk.LabelFrame(options, text="02   FILE FORMATS", style="Card.TLabelframe", padding=13)
        filetypes.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._scroll_targets["filetypes"] = filetypes
        filetypes.columnconfigure(0, weight=1)
        filetypes.columnconfigure(1, weight=1)
        for index, category in enumerate(CATEGORIES):
            row, col = divmod(index, 2)
            ttk.Checkbutton(filetypes, text=category, variable=self.category_vars[category], style="Card.TCheckbutton").grid(row=row, column=col, sticky="w", padx=(0, 12), pady=4)
        type_buttons = ttk.Frame(filetypes, style="Card.TFrame")
        type_buttons.grid(row=5, column=0, columnspan=2, sticky="w", pady=(9, 2))
        ttk.Button(type_buttons, text="Select all", style="Secondary.TButton", command=lambda: self._select_categories(True)).pack(side="left")
        ttk.Button(type_buttons, text="Clear", style="Secondary.TButton", command=lambda: self._select_categories(False)).pack(side="left", padx=(6, 0))
        ttk.Button(type_buttons, text="Choose formats…", style="Dark.TButton", command=self._choose_file_formats).pack(side="left", padx=(6, 0))
        ttk.Label(filetypes, textvariable=self.file_format_summary_var, style="Muted.TLabel", wraplength=480).grid(row=6, column=0, columnspan=2, sticky="w", pady=(7, 0))

        action = ttk.LabelFrame(options, text="03   ORGANIZATION OPTIONS", style="Card.TLabelframe", padding=13)
        action.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ttk.Radiobutton(action, text="Copy files — safest first run", variable=self.mode_var, value="copy", style="Card.TRadiobutton").pack(anchor="w", pady=5)
        ttk.Radiobutton(action, text="Move files", variable=self.mode_var, value="move", style="Card.TRadiobutton").pack(anchor="w", pady=5)
        ttk.Separator(action).pack(fill="x", pady=8)
        ttk.Checkbutton(action, text="Include subfolders", variable=self.recursive_var, style="Card.TCheckbutton").pack(anchor="w", pady=4)
        ttk.Checkbutton(action, text="Read document text where possible", variable=self.content_var, style="Card.TCheckbutton").pack(anchor="w", pady=4)
        ttk.Button(action, text="Add keyword rule…", style="Secondary.TButton", command=self._add_rule).pack(anchor="w", pady=(9, 0))

        selective = ttk.LabelFrame(content, text="04   SELECTIVE TOPIC GROUPS", style="Card.TLabelframe", padding=13)
        selective.pack(fill="x", pady=(0, 12))
        self._scroll_targets["selective"] = selective
        ttk.Checkbutton(selective, text="Only organize files matching the topic groups I select. Leave all other files untouched.",
            variable=self.topic_filter_var, style="Card.TCheckbutton").pack(anchor="w")
        self.topic_options_frame = ttk.Frame(selective, style="Card.TFrame")
        self.topic_options_frame.pack(anchor="w", pady=(8, 0), fill="x")
        self._refresh_topic_options()
        ttk.Button(selective, text="Add / manage topic groups…", style="Secondary.TButton", command=self._manage_topic_groups).pack(anchor="w", pady=(9, 0))
        ttk.Label(selective, text="Create destination folder names and matching keywords. Supported document text can also be searched.",
            style="Muted.TLabel", wraplength=900).pack(anchor="w", pady=(7, 0))

        controls = ttk.Frame(content, style="Page.TFrame")
        controls.pack(fill="x", pady=(0, 12))
        self.scan_button = ttk.Button(controls, text="SCAN & PREVIEW", style="Primary.TButton", command=self._scan)
        self.scan_button.pack(side="left")
        self.discovery_button = ttk.Button(controls, text="Review discovered groups", style="Secondary.TButton", command=self._review_discoveries, state="disabled")
        self.discovery_button.pack(side="left", padx=(8, 0))
        self.teach_button = ttk.Button(controls, text="Teach selected file", style="Secondary.TButton", command=self._teach_selected_file, state="disabled")
        self.teach_button.pack(side="left", padx=(8, 0))
        self.apply_button = ttk.Button(controls, text="APPLY ORGANIZATION", style="Dark.TButton", command=self._apply, state="disabled")
        self.apply_button.pack(side="left", padx=(8, 0))
        self.undo_button = ttk.Button(controls, text="Undo last move", style="Secondary.TButton", command=self._undo)
        self.undo_button.pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Undo automatic move", style="Secondary.TButton", command=self._undo_auto_move).pack(side="left", padx=(6, 0))
        self.automation_button = ttk.Button(controls, text="Start monitor", style="Secondary.TButton", command=self._toggle_automation)
        self.automation_button.pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Open destination", style="Secondary.TButton", command=self._open_output).pack(side="right")

        preview = ttk.LabelFrame(content, text="05   REVIEW PLAN — NOTHING CHANGES UNTIL YOU APPLY", style="Card.TLabelframe", padding=10)
        preview.pack(fill="both", expand=True, pady=(0, 10))
        columns = ("file", "category", "group", "extension", "confidence", "destination")
        self.table = ttk.Treeview(preview, columns=columns, show="headings", height=12)
        headings = {"file":"File", "category":"Type", "group":"Keyword group", "extension":"Extension", "confidence":"Match", "destination":"Planned destination"}
        widths = {"file":180, "category":90, "group":155, "extension":80, "confidence":75, "destination":420}
        for column in columns:
            self.table.heading(column, text=headings[column])
            self.table.column(column, width=widths[column], minwidth=58, stretch=(column == "destination"))
        yscroll = ttk.Scrollbar(preview, orient="vertical", command=self.table.yview)
        xscroll = ttk.Scrollbar(preview, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        preview.rowconfigure(0, weight=1)
        preview.columnconfigure(0, weight=1)
        self.table.bind("<<TreeviewSelect>>", self._preview_selection_changed)

        footer = ttk.Frame(content, style="Page.TFrame")
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.summary_var, style="PageSub.TLabel").pack(anchor="w", pady=(2, 7))
        self.progress = ttk.Progressbar(footer, variable=self.progress_var, maximum=100, mode="indeterminate", style="Red.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(0, 7))
        ttk.Label(footer, textvariable=self.status_var, style="PageSub.TLabel", wraplength=950).pack(anchor="w")
        ttk.Label(footer, textvariable=self.automation_status_var, style="PageSub.TLabel", wraplength=950).pack(anchor="w", pady=(4, 0))
        self._refresh_drives(select_defaults=True)
        self.after(1000, self._refresh_automation_status)

    def _scroll_to_section(self, section: str) -> None:
        target = self._scroll_targets.get(section)
        if target is None:
            return
        self.update_idletasks()
        total = max(1, self.content_frame.winfo_height())
        self.content_canvas.yview_moveto(max(0.0, min(1.0, target.winfo_y() / total)))

    def _open_search_dashboard(self) -> None:
        SearchDashboardDialog(self, CATEGORIES)

    def _open_learning_memory(self) -> None:
        LearningMemoryDialog(self)

    def _preview_selection_changed(self, _event=None) -> None:
        enabled = bool(self.plan and self.table.selection() and not self.busy)
        self.teach_button.configure(state="normal" if enabled else "disabled")

    def _teach_selected_file(self) -> None:
        if not self.plan:
            return
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo("Select a file", "Select a file in the preview first.", parent=self)
            return
        try:
            item = self.plan.files[int(selected[0])]
        except (ValueError, IndexError):
            messagebox.showerror("Selection unavailable", "The selected preview row could not be identified. Run the scan again.", parent=self)
            return
        from tkinter import simpledialog
        suggested_name = simpledialog.askstring(
            "Teach Smart Drive Organizer",
            f"This file was suggested for '{item.topic}'. What folder/topic should similar files use?",
            initialvalue=item.topic,
            parent=self,
        )
        if not suggested_name or not suggested_name.strip():
            return
        phrase = simpledialog.askstring(
            "Remember matching wording",
            "Which word or phrase should identify similar files? You can enter an abbreviation or several words.",
            initialvalue=item.source.stem,
            parent=self,
        )
        if not phrase or not phrase.strip():
            return
        topic = " ".join(suggested_name.split()).strip(" .")
        phrase = " ".join(phrase.split()).strip()
        try:
            rules = load_custom_rules(rules_file())
            existing = next((rule for rule in rules
                             if str(rule.get("name", "")).casefold() == topic.casefold()
                             and str(rule.get("category", "Any")) in ("Any", item.category)), None)
            if existing:
                existing["keywords"] = list(dict.fromkeys(existing.get("keywords", []) + [phrase]))
            else:
                rules.append({"name": topic, "keywords": [phrase], "category": item.category})
            save_custom_rules(rules_file(), rules)
            destination = self.plan.output_root / item.category / topic / item.extension_folder
            record_filing_correction(item.category, phrase, topic, str(item.source), str(destination))
        except Exception as error:
            messagebox.showerror("Could not remember correction", str(error), parent=self)
            return
        messagebox.showinfo(
            "Filing preference remembered",
            f"Smart Drive Organizer will remember that '{phrase}' belongs in '{topic}'. It will apply this preference on the next scan.",
            parent=self,
        )
        self._scan()

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

    def _choose_file_formats(self) -> None:
        categories = self._selected_categories()
        if not categories:
            messagebox.showwarning("Choose a file family", "First select one or more broad file families, such as Documents, Images or Videos.", parent=self)
            return
        dialog = FileTypeSelectionDialog(self, categories, self.extension_filters)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.extension_filters = dialog.result
            try:
                save_extension_filters(self.extension_filters)
            except OSError as error:
                messagebox.showerror("Could not save file-format selection", str(error), parent=self)
                return
            self.file_format_summary_var.set(extension_filter_summary(categories, self.extension_filters))

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.scan_button.configure(state=state)
        self.apply_button.configure(state="disabled" if busy or not self.plan or not self.plan.files else "normal")
        self.teach_button.configure(state="disabled" if busy or not self.plan or not self.plan.files or not self.table.selection() else "normal")
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
            self.discovery_button.configure(state="normal" if result.discovery_groups else "disabled")
            if result.discovery_groups:
                self.status_var.set(f"Found {len(result.discovery_groups):,} new recurring filename pattern(s). Review them before accepting any new group.")
                self.after(180, self._review_discoveries)
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
                + (f"\nLocal search index updated: {data.get('search_index_sync', {}).get('synced', 0):,} file record(s)." if data.get("search_index_sync", {}).get("synced") else "")
                + (f"\nSearch index update warnings: {data.get('search_index_sync', {}).get('failed', 0):,}." if data.get("search_index_sync", {}).get("failed") else "")
            )
        elif self.job_kind == "undo":
            self.status_var.set(f"Undo finished: {result['restored']} restored; {result['skipped']} skipped.")
            messagebox.showinfo("Undo finished", f"Restored: {result['restored']}\nSkipped: {result['skipped']}\n\n" + "\n".join(result.get("errors", [])[:8]))
        self.job_kind = None

    def _show_plan(self, plan: ScanPlan) -> None:
        for row in self.table.get_children():
            self.table.delete(row)
        for index, item in enumerate(plan.files[:MAX_PREVIEW_ROWS]):
            relative = item.destination
            try:
                relative = item.destination.relative_to(plan.output_root)
            except ValueError:
                pass
            self.table.insert("", "end", iid=str(index), values=(
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
            f"{plan.skipped_count:,} skipped; {len(plan.discovery_groups):,} new recurring patterns found. "
            + (f"Showing first {MAX_PREVIEW_ROWS:,} rows." if extra else "")
        )
        self.apply_button.configure(state="normal" if plan.files else "disabled")
        if plan.warnings:
            self.status_var.set(f"Scan completed with {len(plan.warnings)} warning(s). First: {plan.warnings[0]}")
        else:
            self.status_var.set("Scan complete. Review the planned folders, then choose Apply organization.")
        if not plan.files:
            if plan.discovery_groups:
                messagebox.showinfo(
                    "No current topic matches",
                    "No files matched the currently selected topic groups, but the scan found recurring filename patterns. Review the discovered groups to decide whether to add them.",
                    parent=self,
                )
            else:
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
        self.discovery_button.configure(state="disabled")
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
            extension_filters=self.extension_filters,
        ))

    def _review_discoveries(self) -> None:
        if not self.plan or not self.plan.discovery_groups:
            messagebox.showinfo("No discovered groups", "Run a deep scan first. New groups are suggested only when a filename pattern occurs in at least two distinct files.", parent=self)
            return
        dialog = DiscoveryReviewDialog(self, self.plan.discovery_groups)
        self.wait_window(dialog)
        if dialog.result:
            groups = dialog.result.get("groups", [])
            if dialog.result.get("decision") == "rejected":
                record_discovery_decisions([], groups)
                self.status_var.set(f"Remembered {len(groups):,} rejected pattern(s). They will be suppressed in future discovery scans.")
                self._scan()
            else:
                self._approve_discovered_groups(groups)

    def _approve_discovered_groups(self, groups: list[dict]) -> None:
        """Persist approved patterns as reusable classifier rules, then rescan."""
        try:
            record_discovery_decisions(groups, [])
            # Save to the general classifier as well as the selective-topic
            # list so accepted discoveries remain useful when the user changes
            # modes later. The automatic monitor reads these same local rules.
            custom_rules = load_custom_rules(rules_file())
            for group in groups:
                name = str(group["name"]).strip()
                phrase = str(group["phrase"]).strip()
                category = str(group["category"])
                existing = next((rule for rule in custom_rules
                                 if str(rule.get("name", "")).casefold() == name.casefold()
                                 and str(rule.get("category", "Any")) == category), None)
                if existing:
                    existing["keywords"] = list(dict.fromkeys(existing.get("keywords", []) + [phrase]))
                else:
                    custom_rules.append({"name": name, "keywords": [phrase], "category": category})
            save_custom_rules(rules_file(), custom_rules)

            if self.topic_filter_var.get():
                topic_rules = load_topic_rules(topic_rules_file())
                for group in groups:
                    name = str(group["name"]).strip()
                    phrase = str(group["phrase"]).strip()
                    category = str(group["category"])
                    existing = next((rule for rule in topic_rules
                                     if str(rule.get("name", "")).casefold() == name.casefold()), None)
                    if existing:
                        existing["keywords"] = list(dict.fromkeys(existing.get("keywords", []) + [phrase]))
                        scopes = list(existing.get("categories", ["Any"]))
                        existing["categories"] = ["Any"] if "Any" in scopes else list(dict.fromkeys(scopes + [category]))
                    else:
                        topic_rules.append({"name": name, "keywords": [phrase], "categories": [category], "match_mode": "whole_phrase"})
                save_topic_rules(topic_rules_file(), topic_rules)
                self.topic_rules = load_topic_rules(topic_rules_file())
                self._refresh_topic_options()
                for group in groups:
                    name = str(group["name"])
                    if name in self.topic_vars:
                        self.topic_vars[name].set(True)
        except Exception as error:
            messagebox.showerror("Could not save discovered groups", str(error), parent=self)
            return

        self.status_var.set(f"Saved {len(groups):,} approved group rule(s). Running a fresh scan to build the organization preview…")
        self._scan()

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
        self._start_job("apply", lambda progress: self._run_plan_and_sync(plan, mode, progress))

    def _run_plan_and_sync(self, plan: ScanPlan, mode: str, progress: Callable[[str], None]) -> dict:
        result = run_plan(plan, mode, progress)
        try:
            result["search_index_sync"] = sync_journal_actions(result["journal"])
        except Exception:
            # The journal remains authoritative if indexing is unavailable.
            # Search-index errors must never undo successful file actions.
            result["search_index_sync"] = {"synced": 0, "failed": 1}
        return result

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
