from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .learning import forget_rejected_pattern, load_memory, memory_summary


class LearningMemoryDialog(tk.Toplevel):
    """Inspect locally stored learning decisions and reverse rejected suggestions."""
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("Smart Drive Organizer — Learning memory")
        self.geometry("900x650")
        self.minsize(760, 520)
        self.transient(parent)
        self.grab_set()
        bg, black, white, red = "#F4F4F5", "#101010", "#FFFFFF", "#D71920"
        self.configure(bg=bg)
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=black, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=bg, foreground=black, font=("Segoe UI", 19, "bold"))
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background=black, foreground=white, font=("Segoe UI", 9, "bold"), padding=7)
        style.configure("Primary.TButton", background=red, foreground=white, font=("Segoe UI", 9, "bold"), padding=9)
        outer = ttk.Frame(self, padding=16); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Learning memory", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="These preferences are stored locally on this computer. Approved rules also remain in the keyword/topic rule files.", wraplength=850).pack(anchor="w", pady=(4, 10))
        self.summary_var = tk.StringVar()
        ttk.Label(outer, textvariable=self.summary_var).pack(anchor="w", pady=(0, 8))
        self.tabs = ttk.Notebook(outer); self.tabs.pack(fill="both", expand=True)
        self.views = {}
        for key, title, columns in (
            ("approved", "Approved groups", ("name", "phrase", "category", "updated_at")),
            ("rejected", "Rejected suggestions", ("name", "phrase", "category", "updated_at")),
            ("filing_corrections", "Filing corrections", ("topic", "phrase", "category", "destination")),
        ):
            pane = ttk.Frame(self.tabs, padding=8); self.tabs.add(pane, text=title)
            tree = ttk.Treeview(pane, columns=columns, show="headings", height=16)
            labels = {"name":"Folder/group", "phrase":"Remembered wording", "category":"File family",
                      "updated_at":"Last updated", "topic":"Preferred topic", "destination":"Preferred destination"}
            widths = {"name":170, "phrase":210, "category":100, "updated_at":150,
                      "topic":170, "destination":360}
            for col in columns:
                tree.heading(col, text=labels[col]); tree.column(col, width=widths[col], minwidth=65, stretch=(col=="destination"))
            y = ttk.Scrollbar(pane, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=y.set)
            tree.pack(side="left", fill="both", expand=True); y.pack(side="right", fill="y")
            self.views[key] = tree
        self.views["rejected"].bind("<<TreeviewSelect>>", self._rejected_selection)
        self.selected_rejection = None
        actions = ttk.Frame(outer); actions.pack(fill="x", pady=(10, 0))
        self.remove_button = ttk.Button(actions, text="Allow this pattern to be suggested again", command=self._forget_rejection, state="disabled")
        self.remove_button.pack(side="left")
        ttk.Button(actions, text="Refresh", command=self.refresh).pack(side="right")
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right", padx=6)
        self.refresh()

    def refresh(self):
        memory = load_memory()
        summary = memory_summary()
        self.summary_var.set(
            f"Approved groups: {summary['approved_groups']}    "
            f"Rejected patterns: {summary['rejected_groups']}    "
            f"Filing corrections: {summary['filing_corrections']}"
        )
        for key, tree in self.views.items():
            for child in tree.get_children(): tree.delete(child)
            for i, item in enumerate(memory.get(key, [])):
                if key == "filing_corrections":
                    values = (item.get("topic", ""), item.get("phrase", ""), item.get("category", ""), item.get("destination", ""))
                else:
                    values = (item.get("name", ""), item.get("phrase", ""), item.get("category", ""), item.get("updated_at", ""))
                tree.insert("", "end", iid=str(i), values=values)
        self.selected_rejection = None
        self.remove_button.configure(state="disabled")

    def _rejected_selection(self, _event=None):
        tree = self.views["rejected"]
        selected = tree.selection()
        memory = load_memory()
        if not selected:
            self.selected_rejection = None
        else:
            self.selected_rejection = memory["rejected_groups"][int(selected[0])]
        self.remove_button.configure(state="normal" if self.selected_rejection else "disabled")

    def _forget_rejection(self):
        item = self.selected_rejection
        if not item:
            return
        if not messagebox.askyesno(
            "Remove remembered rejection",
            f"Allow '{item.get('phrase')}' to appear as a discovery suggestion again?",
            parent=self,
        ):
            return
        forget_rejected_pattern(str(item.get("category", "Any")), str(item.get("phrase", "")))
        self.refresh()
