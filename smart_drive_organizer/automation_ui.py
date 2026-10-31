from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .classifier import load_topic_rules, save_topic_rules
from .topic_rules_ui import TopicRulesDialog
from .github_publish_ui import GitHubPublishDialog
from .file_types import FileTypeSelectionDialog, extension_filter_summary, save_extension_filters
from .theme import apply_dialog_theme

from .automation import (
    AutomationConfig,
    is_service_running,
    load_settings,
    save_settings,
    set_windows_startup,
    start_background_monitor,
    stop_background_monitor,
    validate_config,
    settings_path,
    topic_rules_path,
)

CATEGORIES = ["Documents", "Images", "Videos", "Audio", "Archives", "Code", "Applications", "Fonts", "3D Models", "Others"]


class AutomationSettingsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, on_saved: Callable[[], None]):
        super().__init__(parent)
        self.parent = parent
        self.on_saved = on_saved
        self.title("Smart Drive Organizer — Automation Settings")
        self.geometry("800x850")
        self.minsize(740, 760)
        self.transient(parent)
        self.grab_set()
        palette = apply_dialog_theme(self, parent)
        self.config_data = load_settings()
        self.extension_filters = dict(self.config_data.extension_filters)
        self.folder_paths = list(self.config_data.monitor_folders)
        self.topic_rules_path = topic_rules_path()
        self.topic_rules = load_topic_rules(self.topic_rules_path)

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Automatic file organization", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Choose the folders to watch. When a new file arrives and finishes downloading, the organizer applies your saved rules automatically.",
            wraplength=730,
        ).pack(anchor="w", pady=(4, 12))

        folders = ttk.LabelFrame(outer, text="1. Folders to monitor", padding=10)
        folders.pack(fill="x", pady=(0, 10))
        self.folder_list = tk.Listbox(folders, height=5, selectmode=tk.EXTENDED, exportselection=False, bg=palette["card"], fg=palette["ink"], selectbackground=palette["red"], selectforeground=palette["white"], highlightthickness=1, highlightbackground=palette["border"])
        self.folder_list.pack(side="left", fill="both", expand=True)
        for value in self.folder_paths:
            self.folder_list.insert("end", value)
        buttons = ttk.Frame(folders)
        buttons.pack(side="left", fill="y", padx=(8, 0))
        ttk.Button(buttons, text="Add folder…", command=self._add_folder).pack(fill="x", pady=(0, 5))
        ttk.Button(buttons, text="Remove selected", command=self._remove_folder).pack(fill="x", pady=5)
        ttk.Button(buttons, text="Add drive root…", command=self._add_drive_root).pack(fill="x", pady=5)
        ttk.Label(
            folders,
            text="Tip: monitor Downloads for browser downloads. Add Desktop, Documents or another folder to monitor files saved there too. You can select a whole drive, but this uses more disk activity.",
            wraplength=700,
        ).pack(anchor="w", pady=(8, 0))

        destination = ttk.LabelFrame(outer, text="2. Organized collection destination", padding=10)
        destination.pack(fill="x", pady=(0, 10))
        self.output_var = tk.StringVar(value=self.config_data.output_folder)
        entry = ttk.Entry(destination, textvariable=self.output_var)
        entry.pack(side="left", fill="x", expand=True)
        ttk.Button(destination, text="Browse…", command=self._browse_output).pack(side="left", padx=(8, 0))

        options = ttk.LabelFrame(outer, text="3. What to organize", padding=10)
        options.pack(fill="x", pady=(0, 10))
        self.category_vars = {
            name: tk.BooleanVar(value=(name in self.config_data.categories))
            for name in CATEGORIES
        }
        for index, category in enumerate(CATEGORIES):
            row, col = divmod(index, 5)
            ttk.Checkbutton(options, text=category, variable=self.category_vars[category]).grid(
                row=row, column=col, sticky="w", padx=(0, 12), pady=3
            )
        self.file_format_summary_var = tk.StringVar(value=extension_filter_summary(self.config_data.categories, self.extension_filters))
        ttk.Button(options, text="Choose file formats…", command=self._choose_file_formats).grid(
            row=2, column=0, sticky="w", pady=(7, 0)
        )
        ttk.Label(options, textvariable=self.file_format_summary_var, wraplength=690).grid(
            row=2, column=1, columnspan=4, sticky="w", padx=(8, 0), pady=(7, 0)
        )
        self.read_content_var = tk.BooleanVar(value=self.config_data.read_document_text)
        ttk.Checkbutton(options, text="Read supported document text for better keyword matching", variable=self.read_content_var).grid(
            row=3, column=0, columnspan=5, sticky="w", pady=(6, 0)
        )

        topics = ttk.LabelFrame(outer, text="4. Optional selective organization — leave all other files untouched", padding=10)
        topics.pack(fill="x", pady=(0, 10))
        self.topic_filter_var = tk.BooleanVar(value=self.config_data.topic_filter_enabled)
        ttk.Checkbutton(
            topics,
            text="Only organize files matching the topic groups selected below; leave all other files untouched",
            variable=self.topic_filter_var,
        ).pack(anchor="w", pady=(0, 5))
        self.topic_options_frame = ttk.Frame(topics)
        self.topic_options_frame.pack(anchor="w", fill="x")
        self.topic_vars: dict[str, tk.BooleanVar] = {}
        self._refresh_topic_options()
        ttk.Button(topics, text="Add / manage my own topic groups…", command=self._manage_topic_groups).pack(anchor="w", pady=(6, 0))
        ttk.Button(topics, text="Publish keyword rules to GitHub…", command=self._publish_topic_rules).pack(anchor="w", pady=(5, 0))
        ttk.Label(
            topics,
            text="Create your own folder labels and add related keywords or phrases. Filename matching works for documents, images, videos, audio and other selected file types. Supported document text can also be searched when enabled.",
            wraplength=730,
        ).pack(anchor="w", pady=(5, 0))

        actions = ttk.LabelFrame(outer, text="5. Automatic action and startup", padding=10)
        actions.pack(fill="x", pady=(0, 10))
        self.mode_var = tk.StringVar(value=self.config_data.mode)
        ttk.Radiobutton(actions, text="Copy files (recommended first)", variable=self.mode_var, value="copy").grid(row=0, column=0, sticky="w", padx=(0, 18), pady=3)
        ttk.Radiobutton(actions, text="Move files into the organized collection", variable=self.mode_var, value="move").grid(row=0, column=1, sticky="w", pady=3)
        self.enabled_var = tk.BooleanVar(value=self.config_data.enabled)
        ttk.Checkbutton(actions, text="Enable automatic monitoring now", variable=self.enabled_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=4)
        self.startup_var = tk.BooleanVar(value=self.config_data.start_with_windows)
        startup = ttk.Checkbutton(actions, text="Start the background monitor automatically when I sign in to Windows", variable=self.startup_var)
        startup.grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        if os.name != "nt":
            startup.configure(state="disabled")
            self.startup_var.set(False)
        ttk.Label(actions, text="Check for new files every").grid(row=3, column=0, sticky="w", pady=(7, 2))
        self.interval_var = tk.StringVar(value=str(self.config_data.poll_interval_seconds))
        ttk.Combobox(actions, textvariable=self.interval_var, values=["5", "10", "15", "30", "60"], state="readonly", width=7).grid(row=3, column=1, sticky="w", pady=(7, 2))
        ttk.Label(actions, text="A file must be stable for several checks before it is handled. Temporary downloads are ignored.", wraplength=700).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        safety = ttk.LabelFrame(outer, text="Important first-run behaviour", padding=10)
        safety.pack(fill="x", pady=(0, 10))
        ttk.Label(
            safety,
            text="The first time a folder is monitored, the program creates an index of files already there but does not automatically move or copy those older files. New files arriving afterwards are organized. Use the normal Scan and preview screen for files already in your folders. Monitoring a whole drive can use noticeable disk activity; Downloads and selected working folders are recommended.",
            wraplength=720,
        ).pack(anchor="w")

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(4, 0))
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Save settings and start", command=self._save,).pack(side="right", padx=8)

    def _available_topic_names(self) -> list[str]:
        names = ["Statements", "Requisitions", "Quotations"]
        for rule in self.topic_rules:
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
            name: tk.BooleanVar(value=previous.get(name, name in self.config_data.selected_topics))
            for name in names
        }
        for index, name in enumerate(names):
            row, col = divmod(index, 4)
            ttk.Checkbutton(self.topic_options_frame, text=name, variable=self.topic_vars[name]).grid(
                row=row, column=col, sticky="w", padx=(0, 18), pady=2
            )

    def _choose_file_formats(self) -> None:
        categories = [name for name, variable in self.category_vars.items() if variable.get()]
        if not categories:
            messagebox.showwarning("Choose a file family", "First select one or more broad file families, such as Documents, Images or Videos.", parent=self)
            return
        dialog = FileTypeSelectionDialog(self, categories, self.extension_filters)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.extension_filters = dialog.result
            self.file_format_summary_var.set(extension_filter_summary(categories, self.extension_filters))

    def _publish_topic_rules(self) -> None:
        GitHubPublishDialog(self, self.topic_rules_path)

    def _manage_topic_groups(self) -> None:
        current = load_topic_rules(self.topic_rules_path)

        def saved(rules: list[dict]) -> None:
            save_topic_rules(self.topic_rules_path, rules)
            self.topic_rules = rules
            self._refresh_topic_options()

        dialog = TopicRulesDialog(self, current, saved)
        self.wait_window(dialog)

    def _add_folder(self) -> None:
        chosen = filedialog.askdirectory(parent=self, title="Choose a folder to monitor", mustexist=True)
        self._insert_folder(chosen)

    def _add_drive_root(self) -> None:
        chosen = filedialog.askdirectory(parent=self, title="Choose a drive root (for example C:\\)", mustexist=True)
        self._insert_folder(chosen)

    def _insert_folder(self, chosen: str) -> None:
        if not chosen:
            return
        path = str(Path(chosen).expanduser().resolve())
        key = os.path.normcase(path)
        if any(os.path.normcase(item) == key for item in self.folder_paths):
            return
        self.folder_paths.append(path)
        self.folder_list.insert("end", path)

    def _remove_folder(self) -> None:
        selected = list(self.folder_list.curselection())
        for index in reversed(selected):
            self.folder_list.delete(index)
            del self.folder_paths[index]

    def _browse_output(self) -> None:
        chosen = filedialog.askdirectory(parent=self, title="Choose the organized collection folder")
        if chosen:
            self.output_var.set(chosen)

    def _save(self) -> None:
        try:
            interval = int(self.interval_var.get())
        except ValueError:
            messagebox.showwarning("Invalid interval", "Choose a monitoring interval.", parent=self)
            return
        selected_categories = [name for name, variable in self.category_vars.items() if variable.get()]
        topic_filter_enabled = self.topic_filter_var.get()
        config = AutomationConfig(
            enabled=self.enabled_var.get(),
            monitor_folders=list(self.folder_paths),
            output_folder=self.output_var.get().strip(),
            categories=selected_categories,
            mode=self.mode_var.get(),
            read_document_text=self.read_content_var.get(),
            start_with_windows=self.startup_var.get() if os.name == "nt" else False,
            poll_interval_seconds=interval,
            stable_observations=self.config_data.stable_observations,
            topic_filter_enabled=topic_filter_enabled,
            selected_topics=[name for name, variable in self.topic_vars.items() if variable.get()],
            extension_filters=self.extension_filters,
        )
        try:
            if config.enabled:
                validate_config(config)
            if config.start_with_windows and not config.enabled:
                raise ValueError("Enable automatic monitoring before enabling Windows startup.")
            save_settings(config)
            save_extension_filters(self.extension_filters)
            set_windows_startup(config.start_with_windows)
        except Exception as error:
            messagebox.showerror("Could not save automation settings", str(error), parent=self)
            return

        was_running = is_service_running()
        if not config.enabled:
            stop_background_monitor()
            messagebox.showinfo("Automation disabled", "Settings saved. Automatic monitoring has been disabled. Any Windows startup entry has also been removed.", parent=self)
            self.on_saved()
            self.destroy()
            return

        if was_running:
            stop_background_monitor()
            self.after(800, lambda: self._restart_when_stopped(config))
        else:
            self._start_saved_monitor()

    def _restart_when_stopped(self, config: AutomationConfig) -> None:
        if is_service_running():
            self.after(500, lambda: self._restart_when_stopped(config))
            return
        self._start_saved_monitor()

    def _start_saved_monitor(self) -> None:
        try:
            pid = start_background_monitor()
        except Exception as error:
            messagebox.showerror("Could not start monitoring", str(error), parent=self)
            return
        self.on_saved()
        messagebox.showinfo(
            "Automation settings saved",
            f"The background monitor has been started (PID {pid}). It runs separately from this window, so you can close the organizer.\n\nThe first scan of each newly added folder only creates a baseline; existing files are left alone. New arrivals are processed after the file is stable.",
            parent=self,
        )
        self.destroy()
