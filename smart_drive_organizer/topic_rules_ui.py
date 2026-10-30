from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import os
from typing import Any, Callable

from .classifier import normalize_topic_rules, safe_folder_name
from .automation import topic_rules_path
from .github_publish import should_offer_github_publish
from .github_publish_ui import GitHubPublishDialog

CATEGORIES = ["Documents", "Images", "Videos", "Audio", "Archives", "Code", "Applications", "Fonts", "3D Models", "Others"]


class TopicRulesDialog(tk.Toplevel):
    """Editor for user-defined selective topic folders and matching phrases."""

    def __init__(self, parent: tk.Misc, rules: list[dict[str, Any]], on_saved: Callable[[list[dict[str, Any]]], None]):
        super().__init__(parent)
        self.title("Manage custom topic groups")
        self.geometry("1020x760")
        self.minsize(900, 680)
        self.transient(parent)
        self.grab_set()
        self.on_saved = on_saved
        self.rules = normalize_topic_rules(rules)
        self.original_rules = normalize_topic_rules(rules)
        self._selected_index: int | None = None

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Create your own topic folders", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Give the group a folder name, then enter words or phrases that identify matching files. Use commas or new lines between phrases. Matching is based on filenames for all file types and supported document text for documents.",
            wraplength=770,
        ).pack(anchor="w", pady=(4, 10))

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        left = ttk.LabelFrame(body, text="Saved topic groups", padding=8)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.tree = ttk.Treeview(left, columns=("scope", "match", "destination", "keywords"), show="tree headings", height=13)
        self.tree.heading("#0", text="Folder name")
        self.tree.heading("scope", text="File category")
        self.tree.heading("match", text="Match")
        self.tree.heading("destination", text="Destination")
        self.tree.heading("keywords", text="Matching keywords")
        self.tree.column("#0", width=135, minwidth=110)
        self.tree.column("scope", width=75, minwidth=70)
        self.tree.column("match", width=70, minwidth=65)
        self.tree.column("destination", width=185, minwidth=130)
        self.tree.column("keywords", width=190, minwidth=145)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._load_selection)

        right = ttk.LabelFrame(body, text="Add or edit a topic", padding=10)
        right.pack(side="left", fill="both", expand=True)
        self.name_var = tk.StringVar()
        self.category_var = tk.StringVar(value="Any")
        self.match_mode_var = tk.StringVar(value="Contains (partial keyword)")
        self.destination_var = tk.StringVar()
        ttk.Label(right, text="Folder name").pack(anchor="w")
        ttk.Entry(right, textvariable=self.name_var).pack(fill="x", pady=(3, 10))
        ttk.Label(right, text="Apply to file category").pack(anchor="w")
        ttk.Combobox(right, textvariable=self.category_var, values=["Any"] + CATEGORIES, state="readonly").pack(fill="x", pady=(3, 9))
        ttk.Label(right, text="Keyword matching").pack(anchor="w")
        ttk.Combobox(
            right,
            textvariable=self.match_mode_var,
            values=["Contains (partial keyword)", "Whole word / phrase"],
            state="readonly",
        ).pack(fill="x", pady=(3, 9))
        ttk.Label(right, text="Send matching files to this exact folder (optional)").pack(anchor="w")
        destination_row = ttk.Frame(right)
        destination_row.pack(fill="x", pady=(3, 3))
        ttk.Entry(destination_row, textvariable=self.destination_var).pack(side="left", fill="x", expand=True)
        ttk.Button(destination_row, text="Browse…", command=self._browse_destination).pack(side="left", padx=(6, 0))
        ttk.Label(right, text="Leave blank to use the main Organized Output / Category / Topic / Extension structure. A custom destination receives matching files directly.", wraplength=340).pack(anchor="w", pady=(0, 9))
        ttk.Label(right, text="Keywords and phrases (commas or new lines)").pack(anchor="w")
        self.keywords_text = tk.Text(right, height=6, wrap="word", font=("Segoe UI", 9))
        self.keywords_text.pack(fill="both", expand=True, pady=(3, 5))
        ttk.Label(right, text="Example: QUO, quotation, quote number. With Contains, QUO matches Quotation - S01610.", wraplength=340).pack(anchor="w", pady=(0, 8))
        ttk.Button(right, text="Add / update topic", command=self._upsert).pack(fill="x", pady=3)
        ttk.Button(right, text="Clear fields", command=self._clear).pack(fill="x", pady=3)
        ttk.Button(right, text="Remove selected topic", command=self._remove).pack(fill="x", pady=3)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Label(footer, text="Unselected topics and files that do not match remain untouched.").pack(side="left")
        ttk.Button(footer, text="Publish to GitHub…", command=self._publish_to_github).pack(side="left")
        ttk.Button(footer, text="Close without saving", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Save topic groups", command=self._save).pack(side="right", padx=8)
        self._refresh_tree()

    def _refresh_tree(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, rule in enumerate(self.rules):
            scopes = rule.get("categories", ["Any"])
            scope_text = "All types" if "Any" in scopes else ", ".join(scopes)
            keywords = ", ".join(rule.get("keywords", []))
            match_text = "Contains" if rule.get("match_mode", "whole_phrase") == "contains" else "Whole"
            destination = str(rule.get("destination", "")).strip()
            destination_text = destination if destination else "Main output"
            self.tree.insert("", "end", iid=str(index), text=rule["name"], values=(scope_text, match_text, destination_text, keywords))

    def _load_selection(self, _event: object = None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        try:
            index = int(selected[0])
            rule = self.rules[index]
        except (ValueError, IndexError):
            return
        self._selected_index = index
        self.name_var.set(rule["name"])
        scopes = rule.get("categories", ["Any"])
        self.category_var.set("Any" if "Any" in scopes else (scopes[0] if scopes else "Any"))
        self.keywords_text.delete("1.0", "end")
        self.keywords_text.insert("1.0", "\n".join(rule.get("keywords", [])))
        self.destination_var.set(str(rule.get("destination", "")))
        self.match_mode_var.set("Contains (partial keyword)" if rule.get("match_mode", "whole_phrase") == "contains" else "Whole word / phrase")

    def _clear(self) -> None:
        self._selected_index = None
        self.name_var.set("")
        self.category_var.set("Any")
        self.match_mode_var.set("Contains (partial keyword)")
        self.destination_var.set("")
        self.keywords_text.delete("1.0", "end")
        self.tree.selection_remove(self.tree.selection())

    def _browse_destination(self) -> None:
        chosen = filedialog.askdirectory(parent=self, title="Choose the permanent destination folder", mustexist=True)
        if chosen:
            self.destination_var.set(chosen)

    def _upsert(self) -> None:
        raw_name = self.name_var.get().strip()
        name = safe_folder_name(raw_name)
        phrases = [part.strip() for part in self.keywords_text.get("1.0", "end").replace(";", "\n").replace(",", "\n").splitlines() if part.strip()]
        if not raw_name or name == "Unclassified" or not phrases:
            messagebox.showwarning("Missing details", "Enter a folder name and at least one keyword or phrase.", parent=self)
            return
        category = self.category_var.get()
        categories = ["Any"] if category == "Any" else [category]
        destination = self.destination_var.get().strip()
        if destination:
            destination_path = Path(os.path.expandvars(destination)).expanduser()
            if destination_path.exists() and not destination_path.is_dir():
                messagebox.showwarning("Invalid destination", "The selected destination exists as a file. Choose a folder.", parent=self)
                return
            if destination_path.resolve() == destination_path.resolve().parent:
                messagebox.showwarning("Invalid destination", "Choose a named folder, not the root of a drive.", parent=self)
                return
        match_mode = "contains" if self.match_mode_var.get().startswith("Contains") else "whole_phrase"
        normalized = normalize_topic_rules([{
            "name": name,
            "keywords": phrases,
            "categories": categories,
            "destination": destination,
            "match_mode": match_mode,
        }])
        if not normalized:
            messagebox.showwarning("Invalid topic", "The topic name or keywords could not be accepted.", parent=self)
            return
        updated = normalized[0]
        if self._selected_index is not None and self._selected_index < len(self.rules):
            # Don't allow two independently editable rows with the same label.
            duplicate = next((i for i, rule in enumerate(self.rules) if i != self._selected_index and rule["name"].casefold() == name.casefold()), None)
            if duplicate is not None:
                messagebox.showwarning("Topic already exists", "A topic with this folder name already exists. Select that row to edit it.", parent=self)
                return
            self.rules[self._selected_index] = updated
        else:
            existing = next((i for i, rule in enumerate(self.rules) if rule["name"].casefold() == name.casefold()), None)
            if existing is not None:
                messagebox.showwarning("Topic already exists", "A topic with this folder name already exists. Select that row to edit it.", parent=self)
                return
            self.rules.append(updated)
        self.rules = normalize_topic_rules(self.rules)
        self._refresh_tree()
        self._clear()

    def _remove(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        index = int(selected[0])
        if 0 <= index < len(self.rules):
            self.rules.pop(index)
        self._refresh_tree()
        self._clear()

    def _save(self) -> None:
        self.rules = normalize_topic_rules(self.rules)
        changed = self.rules != self.original_rules
        try:
            self.on_saved(self.rules)
        except Exception as error:
            messagebox.showerror("Could not save topics", str(error), parent=self)
            return
        should_prompt = should_offer_github_publish(self.original_rules, self.rules)
        should_publish = False
        if should_prompt:
            should_publish = messagebox.askyesno(
                "Publish keyword changes to GitHub?",
                "Your keyword groups have been saved permanently on this computer.\n\n"
                "Would you like to publish the updated shared keyword rules to your GitHub repository now?\n\n"
                "You will review the repository and confirm the push before anything is uploaded.",
                parent=self,
            )
        parent = self.master
        self.destroy()
        if should_publish and parent is not None:
            parent.after(100, lambda: GitHubPublishDialog(parent, topic_rules_path()))

    def _publish_to_github(self) -> None:
        parent = self.master
        self.destroy()
        if parent is not None:
            parent.after(100, lambda: GitHubPublishDialog(parent, topic_rules_path()))
