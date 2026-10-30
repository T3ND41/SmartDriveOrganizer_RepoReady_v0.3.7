from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from .classifier import load_topic_rules
from .github_publish import (
    GitHubPublishError,
    connect_github_repository,
    inspect_github_repository,
    load_github_settings,
    normalize_github_repository_url,
    preview_application_update_to_github,
    project_source_root,
    publish_application_update_to_github,
    publish_topic_rules_to_github,
    save_github_settings,
)


class GitHubPublishDialog(tk.Toplevel):
    """Connect by pasting a GitHub URL and explicitly publish rules or app source."""

    def __init__(self, parent: tk.Misc, rules_path: Path):
        super().__init__(parent)
        self.parent = parent
        self.rules_path = rules_path
        self.settings: dict[str, Any] = load_github_settings()
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.pending_source_settings: dict[str, Any] | None = None
        self.title("GitHub publishing")
        self.geometry("820x650")
        self.minsize(740, 590)
        self.transient(parent)
        self.grab_set()

        legacy_url = ""
        legacy_path = self.settings.get("repository_path", "")
        if legacy_path and Path(legacy_path).is_dir():
            try:
                legacy_url = inspect_github_repository(legacy_path)["remote"]
            except Exception:
                legacy_url = ""
        initial_url = self.settings.get("repository_url", "") or legacy_url

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Connect your GitHub repository", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "Paste the main URL of your GitHub repository once. Smart Drive Organizer will clone it into its "
                "own application-data folder and remember the connection. After that, use the publish buttons below."
            ),
            wraplength=770,
        ).pack(anchor="w", pady=(5, 12))

        repo_box = ttk.LabelFrame(outer, text="1. GitHub repository URL", padding=10)
        repo_box.pack(fill="x", pady=(0, 10))
        self.repo_var = tk.StringVar(value=initial_url)
        ttk.Entry(repo_box, textvariable=self.repo_var).pack(fill="x")
        ttk.Label(
            repo_box,
            text="Example: https://github.com/YOUR-USERNAME/YOUR-REPOSITORY  (HTTPS and SSH URLs are supported)",
            wraplength=740,
        ).pack(anchor="w", pady=(4, 6))
        button_row = ttk.Frame(repo_box)
        button_row.pack(fill="x")
        self.connect_button = ttk.Button(button_row, text="Save URL & connect", command=self._connect_repo)
        self.connect_button.pack(side="left")
        ttk.Button(button_row, text="Save settings only", command=self._save_settings).pack(side="left", padx=7)
        self.workspace_var = tk.StringVar(value="Repository checkout: not connected yet")
        if initial_url:
            try:
                saved_workspace = Path(self.settings.get("repository_path", "")) if self.settings.get("repository_path") else None
                if saved_workspace and saved_workspace.is_dir():
                    connected_info = inspect_github_repository(saved_workspace)
                else:
                    from .github_publish import default_repository_workspace_path
                    candidate = default_repository_workspace_path(initial_url)
                    connected_info = inspect_github_repository(candidate) if candidate.is_dir() else None
                if connected_info:
                    self.workspace_var.set(f"Connected: {connected_info['remote']} | Branch: {connected_info['branch']}\nLocal checkout: {connected_info['path']}")
            except Exception:
                pass
        ttk.Label(repo_box, textvariable=self.workspace_var, wraplength=740).pack(anchor="w", pady=(7, 0))

        identity = ttk.LabelFrame(outer, text="2. Git commit identity", padding=10)
        identity.pack(fill="x", pady=(0, 10))
        self.name_var = tk.StringVar(value=self.settings.get("author_name", ""))
        self.email_var = tk.StringVar(value=self.settings.get("author_email", ""))
        ttk.Label(identity, text="Name").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(identity, textvariable=self.name_var, width=32).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(identity, text="Email").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(identity, textvariable=self.email_var, width=32).grid(row=1, column=1, sticky="ew", pady=4)
        identity.columnconfigure(1, weight=1)
        ttk.Label(
            identity,
            text="Used as the author of Git commits. No GitHub password or access token is stored by this application.",
            wraplength=740,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 0))

        prefs = ttk.LabelFrame(outer, text="3. Publishing preference", padding=10)
        prefs.pack(fill="x", pady=(0, 10))
        self.ask_var = tk.BooleanVar(value=bool(self.settings.get("ask_after_rule_changes", True)))
        ttk.Checkbutton(
            prefs,
            text="Ask whether to publish after I save changes to keyword groups",
            variable=self.ask_var,
        ).pack(anchor="w")

        actions = ttk.LabelFrame(outer, text="4. Publish an approved update", padding=10)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Label(
            actions,
            text=(
                "Keyword rules publish the shared group names and keywords. Application source publishes the approved "
                "program files (Python modules, tests, launcher and documentation) after showing you a file-change preview."
            ),
            wraplength=740,
        ).pack(anchor="w", pady=(0, 8))
        self.commit_message_var = tk.StringVar(value="Update Smart Drive Organizer application")
        ttk.Label(actions, text="Application update commit message (optional)").pack(anchor="w")
        ttk.Entry(actions, textvariable=self.commit_message_var).pack(fill="x", pady=(3, 8))
        action_row = ttk.Frame(actions)
        action_row.pack(fill="x")
        self.publish_rules_button = ttk.Button(action_row, text="Publish keyword rules", command=self._publish_rules)
        self.publish_rules_button.pack(side="left")
        self.publish_source_button = ttk.Button(action_row, text="Preview / publish app source update…", command=self._preview_source)
        self.publish_source_button.pack(side="left", padx=8)

        self.status_var = tk.StringVar(
            value=(
                "First-time setup: install Git for Windows or GitHub Desktop, sign in to GitHub once, then paste your "
                "repository URL and choose Save URL & connect. For GitHub CLI authentication, use: gh auth login, then gh auth setup-git."
            )
        )
        ttk.Label(outer, textvariable=self.status_var, wraplength=770).pack(anchor="w", pady=(2, 10))

        footer = ttk.Frame(outer)
        footer.pack(fill="x", side="bottom")
        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right")
        self.after(120, self._poll)

    def _collect_settings(self) -> dict[str, Any]:
        url = self.repo_var.get().strip()
        if url:
            url = normalize_github_repository_url(url)
        return {
            "repository_url": url,
            # Kept for migration compatibility with earlier releases. New setups use repository_url.
            "repository_path": self.settings.get("repository_path", "") if not url else "",
            "author_name": self.name_var.get().strip(),
            "author_email": self.email_var.get().strip(),
            "ask_after_rule_changes": self.ask_var.get(),
        }

    def _repository_reference(self, settings: dict[str, Any]) -> str:
        return str(settings.get("repository_url", "")).strip() or str(settings.get("repository_path", "")).strip()

    def _save_settings(self) -> bool:
        try:
            settings = self._collect_settings()
            save_github_settings(settings)
            self.settings.update(settings)
        except Exception as error:
            messagebox.showerror("GitHub publishing settings", str(error), parent=self)
            return False
        self.status_var.set("GitHub settings saved on this computer.")
        return True

    def _set_busy(self, busy: bool, message: str) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.connect_button.configure(state=state)
        self.publish_rules_button.configure(state=state)
        self.publish_source_button.configure(state=state)
        self.status_var.set(message)

    def _connect_repo(self) -> None:
        if self.busy:
            return
        try:
            settings = self._collect_settings()
            if not settings["repository_url"]:
                raise GitHubPublishError("Paste your GitHub repository URL first.")
            save_github_settings(settings)
            self.settings.update(settings)
        except Exception as error:
            messagebox.showerror("GitHub connection settings", str(error), parent=self)
            return
        self._set_busy(True, "Saving your repository URL and connecting to GitHub…")

        def worker() -> None:
            try:
                info = connect_github_repository(settings["repository_url"])
                self.events.put(("connected", info))
            except Exception as error:
                self.events.put(("error", str(error)))

        threading.Thread(target=worker, name="sdo-github-connect", daemon=True).start()

    def _publish_rules(self) -> None:
        if self.busy:
            return
        try:
            settings = self._collect_settings()
            reference = self._repository_reference(settings)
            if not reference:
                raise GitHubPublishError("Paste your GitHub repository URL and select Save URL & connect first.")
            rules = load_topic_rules(self.rules_path)
            if not rules:
                raise GitHubPublishError("There are no custom keyword groups to publish yet. Add and save a topic group first.")
            save_github_settings(settings)
            self.settings.update(settings)
        except Exception as error:
            messagebox.showerror("Cannot publish keyword rules", str(error), parent=self)
            return

        if not messagebox.askyesno(
            "Confirm GitHub push — keyword rules",
            "Publish your saved keyword groups to the configured GitHub repository now?\n\n"
            "Only config/published_topic_rules.json will be committed. Downloaded files, personal settings, local databases, "
            "logs and absolute destination paths will not be uploaded.",
            icon="warning", parent=self,
        ):
            return
        self._set_busy(True, "Preparing a rules-only commit and contacting GitHub…")

        def worker() -> None:
            try:
                result = publish_topic_rules_to_github(
                    reference, rules, settings.get("author_name", ""), settings.get("author_email", "")
                )
                self.events.put(("done", result))
            except Exception as error:
                self.events.put(("error", str(error)))

        threading.Thread(target=worker, name="sdo-github-rules-publish", daemon=True).start()

    def _preview_source(self) -> None:
        if self.busy:
            return
        try:
            settings = self._collect_settings()
            reference = self._repository_reference(settings)
            if not reference:
                raise GitHubPublishError("Paste your GitHub repository URL and select Save URL & connect first.")
            save_github_settings(settings)
            self.settings.update(settings)
        except Exception as error:
            messagebox.showerror("Cannot prepare application update", str(error), parent=self)
            return
        self._set_busy(True, "Comparing approved application source files with your GitHub repository…")

        def worker() -> None:
            try:
                preview = preview_application_update_to_github(reference, project_source_root())
                self.events.put(("source_preview", (settings, reference, preview)))
            except Exception as error:
                self.events.put(("error", str(error)))

        threading.Thread(target=worker, name="sdo-github-source-preview", daemon=True).start()

    def _confirm_source_publish(self, settings: dict[str, Any], reference: str, preview: dict[str, Any]) -> None:
        added = preview.get("added", [])
        updated = preview.get("updated", [])
        if not preview.get("total_changes", 0):
            messagebox.showinfo(
                "Application source is up to date",
                "There are no approved source-code changes to publish.", parent=self,
            )
            return
        lines = []
        if added:
            lines.append("NEW FILES:\n" + "\n".join(f"  + {item}" for item in added))
        if updated:
            lines.append("UPDATED FILES:\n" + "\n".join(f"  ~ {item}" for item in updated))
        details = "\n\n".join(lines)
        if len(details) > 6500:
            details = details[:6500] + "\n… (list shortened)"
        approved = messagebox.askyesno(
            "Review application update before pushing",
            f"The following approved application files will be committed to GitHub:\n\n{details}\n\n"
            "The publisher excludes personal keyword settings, drive paths, databases, logs, downloaded files, and arbitrary files. "
            "It will not delete remote files that are absent from this installation.\n\nProceed with this source-code commit and push?",
            icon="warning", parent=self,
        )
        if not approved:
            self.status_var.set("Application source publishing cancelled. No source update was pushed.")
            return
        self._set_busy(True, "Publishing the reviewed application source update…")
        commit_message = self.commit_message_var.get().strip() or "Update Smart Drive Organizer application"

        def worker() -> None:
            try:
                result = publish_application_update_to_github(
                    reference, project_source_root(), settings.get("author_name", ""),
                    settings.get("author_email", ""), commit_message,
                )
                self.events.put(("done", result))
            except Exception as error:
                self.events.put(("error", str(error)))

        threading.Thread(target=worker, name="sdo-github-source-publish", daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "source_preview":
                    self._set_busy(False, "Application source preview ready. Review the proposed files before publishing.")
                    settings, reference, preview = payload
                    self._confirm_source_publish(settings, reference, preview)
                    continue
                self._set_busy(False, "Ready.")
                if kind == "error":
                    self.status_var.set("The GitHub action did not complete. Review the message below.")
                    messagebox.showerror("GitHub action failed", str(payload), parent=self)
                elif kind == "connected":
                    info = payload
                    workspace = Path(info["path"])
                    self.workspace_var.set(f"Connected: {info['remote']} | Branch: {info['branch']}\nLocal checkout: {workspace}")
                    self.status_var.set("Repository connected and saved. You can now publish keyword rules or review an application update.")
                    messagebox.showinfo("GitHub connected", "Your repository URL is saved. You can now publish updates using the buttons in this window.", parent=self)
                else:
                    result = payload
                    self.status_var.set(str(result.get("message", "Finished.")))
                    status = result.get("status")
                    if status == "pushed":
                        messagebox.showinfo("Published to GitHub", str(result.get("message")), parent=self)
                    elif status == "unchanged":
                        messagebox.showinfo("No update needed", str(result.get("message")), parent=self)
                    else:
                        messagebox.showwarning("Committed locally; push incomplete", str(result.get("message")), parent=self)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(150, self._poll)
