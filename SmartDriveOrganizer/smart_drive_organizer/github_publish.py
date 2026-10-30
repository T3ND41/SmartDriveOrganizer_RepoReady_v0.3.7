from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PureWindowsPath
from typing import Any, Optional
from urllib.parse import urlparse

from .automation import app_data_dir
from .classifier import normalize_topic_rules

PUBLISHED_RULES_RELATIVE_PATH = Path("config") / "published_topic_rules.json"

# Only these application-owned source files may be copied to the GitHub checkout.
# Runtime settings, databases, logs, personal rules, and source documents are excluded.
PUBLISHABLE_SOURCE_PATTERNS = (
    "run.py",
    "pyproject.toml",
    "README.md",
    "CHANGELOG.md",
    "LICENSE.txt",
    "PUBLISHING_TO_GITHUB.md",
    "REPOSITORY_SETUP.md",
    "INSTALLER_ENDPOINTS.txt",
    "START_HERE.txt",
    "Start_SmartDriveOrganizer.bat",
    "PUSH_TO_GITHUB.bat",
    ".gitignore",
    "requirements-content.txt",
    "install.ps1",
    "SECURITY.md",
    "VERSION.txt",
    "scripts/*.ps1",
    ".github/workflows/*.yml",
    "cloudflare/*.js",
    "cloudflare/*.toml",
    "cloudflare/*.md",
    "smart_drive_organizer/*.py",
    "tests/*.py",
    "config/topic_rules.example.json",
)
_SECRET_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
)


class GitHubPublishError(RuntimeError):
    """A safe, actionable Git/GitHub publishing error."""


def github_settings_path() -> Path:
    return app_data_dir() / "github_publish_settings.json"


def load_github_settings(path: Optional[Path] = None) -> dict[str, Any]:
    target = path or github_settings_path()
    defaults: dict[str, Any] = {
        "repository_url": "", "repository_path": "", "author_name": "", "author_email": "",
        "ask_after_rule_changes": True,
    }
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            defaults.update({key: value.get(key, default) for key, default in defaults.items()})
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    # Migrate older releases that stored a URL in the repository_path field.
    old_path = str(defaults.get("repository_path", "")).strip()
    if old_path and not defaults.get("repository_url") and _looks_like_github_url(old_path):
        defaults["repository_url"] = old_path
        defaults["repository_path"] = ""
    for key in ("repository_url", "repository_path", "author_name", "author_email"):
        defaults[key] = str(defaults.get(key, ""))
    defaults["ask_after_rule_changes"] = bool(defaults.get("ask_after_rule_changes", True))
    return defaults


def should_offer_github_publish(
    original_rules: list[dict[str, Any]],
    updated_rules: list[dict[str, Any]],
    settings: Optional[dict[str, Any]] = None,
) -> bool:
    """Return True when changed, saved topic rules should trigger a publish prompt."""
    preferences = settings if settings is not None else load_github_settings()
    if not bool(preferences.get("ask_after_rule_changes", True)):
        return False
    return normalize_topic_rules(original_rules) != normalize_topic_rules(updated_rules)


def save_github_settings(settings: dict[str, Any], path: Optional[Path] = None) -> Path:
    target = path or github_settings_path()
    current = load_github_settings(target)
    current.update({key: settings[key] for key in current if key in settings})
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".github-settings-", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(current, handle, ensure_ascii=False, indent=2)
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


def _git(args: list[str], cwd: Optional[Path] = None, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("git")
    if not executable:
        raise GitHubPublishError(
            "Git was not found. Install Git for Windows (or GitHub Desktop, which includes Git), then reopen Smart Drive Organizer."
        )
    try:
        return subprocess.run(
            [executable, *args], cwd=str(cwd) if cwd else None, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout, shell=False,
        )
    except subprocess.TimeoutExpired as error:
        raise GitHubPublishError(f"Git command timed out: git {' '.join(args)}") from error
    except OSError as error:
        raise GitHubPublishError(f"Could not run Git: {error}") from error


def _git_output(args: list[str], cwd: Optional[Path] = None, timeout: int = 45) -> str:
    result = _git(args, cwd=cwd, timeout=timeout)
    if result.returncode != 0:
        raise GitHubPublishError((result.stderr or result.stdout or "Git returned an unspecified error.").strip())
    return result.stdout.strip()


def _looks_like_github_url(value: str) -> bool:
    return bool(re.match(r"^(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)", value.strip(), re.IGNORECASE))


def github_repository_identity(value: str) -> tuple[str, str]:
    """Extract the owner/repository identity from HTTPS, SSH, or scp-style GitHub URLs."""
    text = value.strip()
    match = re.fullmatch(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?/?", text, flags=re.IGNORECASE)
    if match:
        owner, repo = match.groups()
    else:
        try:
            parsed = urlparse(text)
        except ValueError as error:
            raise GitHubPublishError("Enter a valid GitHub repository URL.") from error
        if (parsed.hostname or "").casefold() != "github.com":
            raise GitHubPublishError("The repository URL must point to github.com.")
        if parsed.username not in (None, "", "git") or parsed.password:
            raise GitHubPublishError("Do not include a username, password, or access token in the repository URL.")
        if parsed.scheme not in {"https", "ssh"}:
            raise GitHubPublishError("Use an HTTPS or SSH GitHub repository URL.")
        if parsed.query or parsed.fragment:
            raise GitHubPublishError("Paste the repository's main URL, without query strings or page fragments.")
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) != 2:
            raise GitHubPublishError("Paste the repository's main URL, for example https://github.com/OWNER/REPOSITORY.")
        owner, repo = parts
    repo = re.sub(r"\.git$", "", repo, flags=re.IGNORECASE)
    safe_part = re.compile(r"^[A-Za-z0-9_.-]+$")
    if not safe_part.fullmatch(owner) or not safe_part.fullmatch(repo) or owner in {".", ".."} or repo in {".", ".."}:
        raise GitHubPublishError("The GitHub URL contains an invalid owner or repository name.")
    return owner.casefold(), repo.casefold()


def normalize_github_repository_url(value: str) -> str:
    """Validate and return a trimmed GitHub repository URL without embedded credentials."""
    text = value.strip()
    if not text:
        raise GitHubPublishError("Paste your GitHub repository URL first.")
    github_repository_identity(text)
    return text.rstrip("/")


def default_repository_workspace_path(repository_url: str, base_dir: Optional[Path] = None) -> Path:
    owner, repo = github_repository_identity(repository_url)
    parent = base_dir or (app_data_dir() / "github_repositories")
    return Path(parent) / f"{owner}__{repo}"


def _is_github_remote(remote: str) -> bool:
    try:
        github_repository_identity(remote)
        return True
    except GitHubPublishError:
        return False


def _same_github_repository(left: str, right: str) -> bool:
    try:
        return github_repository_identity(left) == github_repository_identity(right)
    except GitHubPublishError:
        return False


def inspect_github_repository(repository_path: str | Path) -> dict[str, str]:
    selected = Path(repository_path).expanduser().resolve()
    if not selected.exists() or not selected.is_dir():
        raise GitHubPublishError("The local GitHub checkout does not exist yet. Connect using your repository URL first.")
    top = Path(_git_output(["rev-parse", "--show-toplevel"], cwd=selected)).resolve()
    if os.path.normcase(str(top)) != os.path.normcase(str(selected)):
        raise GitHubPublishError(f"The selected folder is not the repository's top-level folder:\n{top}")
    remote = _git_output(["remote", "get-url", "origin"], cwd=top)
    if not _is_github_remote(remote):
        raise GitHubPublishError("The repository's 'origin' remote is not a GitHub URL.")
    branch = _git_output(["branch", "--show-current"], cwd=top)
    if not branch:
        raise GitHubPublishError("The repository is in detached-HEAD mode. Check out a branch before publishing.")
    return {"path": str(top), "remote": remote, "branch": branch}


def connect_github_repository(repository_url: str, workspace_path: Optional[str | Path] = None) -> dict[str, str]:
    """Clone the pasted repository URL once into app data, or validate its existing checkout."""
    url = normalize_github_repository_url(repository_url)
    target = Path(workspace_path) if workspace_path else default_repository_workspace_path(url)
    target = target.expanduser().resolve()
    if target.exists():
        if target.is_dir() and not any(target.iterdir()):
            target.rmdir()
        else:
            info = inspect_github_repository(target)
            if not _same_github_repository(info["remote"], url):
                raise GitHubPublishError(
                    "The saved local checkout belongs to a different GitHub repository. "
                    "Change the repository URL or choose a new checkout location."
                )
            return info
    target.parent.mkdir(parents=True, exist_ok=True)
    target_created_by_this_call = not target.exists()
    clone = _git(["clone", "--", url, str(target)], cwd=None, timeout=300)
    if clone.returncode != 0:
        detail = (clone.stderr or clone.stdout or "Git clone failed.").strip()
        # Remove only a partial checkout created by this invocation; never touch a pre-existing folder.
        if target_created_by_this_call and target.exists() and target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        if "authentication" in detail.casefold() or "permission denied" in detail.casefold() or "could not read" in detail.casefold():
            raise GitHubPublishError(
                "GitHub did not authorize the clone. Sign in once using GitHub Desktop / Git Credential Manager, "
                "or GitHub CLI, then press Connect again. Do not paste a token into the app.\n\n" + detail
            )
        raise GitHubPublishError(f"Could not clone the GitHub repository. Check the URL and your internet connection.\n{detail}")
    # GitHub permits repositories to be created empty. Give such a checkout
    # an initial local branch so the first approved publish can create it remotely.
    current_branch = _git(["branch", "--show-current"], cwd=target)
    if current_branch.returncode == 0 and not current_branch.stdout.strip():
        head_check = _git(["rev-parse", "--verify", "HEAD"], cwd=target)
        if head_check.returncode != 0:
            init_branch = _git(["checkout", "-b", "main"], cwd=target)
            if init_branch.returncode != 0:
                raise GitHubPublishError((init_branch.stderr or init_branch.stdout or "Could not initialize a branch in the empty repository.").strip())
    info = inspect_github_repository(target)
    if not _same_github_repository(info["remote"], url):
        raise GitHubPublishError("The cloned repository's origin does not match the URL you entered.")
    return info


def resolve_repository_reference(repository_reference: str | Path) -> dict[str, str]:
    value = str(repository_reference).strip()
    if _looks_like_github_url(value):
        return connect_github_repository(value)
    return inspect_github_repository(value)


def _is_absolute_destination(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    return (
        Path(text).is_absolute() or PureWindowsPath(text).is_absolute()
        or bool(re.match(r"^[A-Za-z]:[\\/]", text))
        or text.startswith(("\\\\", "//", "~/", "%"))
    )


def build_published_rules_payload(rules: list[dict[str, Any]]) -> dict[str, Any]:
    """Share rule definitions while omitting machine-specific absolute paths."""
    safe_rules: list[dict[str, Any]] = []
    for rule in normalize_topic_rules(rules):
        item: dict[str, Any] = {
            "name": rule["name"], "keywords": list(rule["keywords"]),
            "categories": list(rule["categories"]), "match_mode": rule["match_mode"],
        }
        destination = str(rule.get("destination", "")).strip()
        if destination and not _is_absolute_destination(destination):
            item["destination"] = destination
        safe_rules.append(item)
    return {"schema_version": 1, "application": "Smart Drive Organizer", "rules": safe_rules}


def _status_paths(status: str) -> set[str]:
    paths: set[str] = set()
    for line in status.splitlines():
        if len(line) < 4:
            continue
        value = line[3:].strip()
        if " -> " in value:
            value = value.rsplit(" -> ", 1)[-1]
        paths.add(value.strip('"').replace("\\", "/"))
    return paths


def _assert_clean_repository(repo: Path, allowed_dirty: Optional[set[str]] = None) -> None:
    status = _git_output(["status", "--porcelain", "--untracked-files=all"], cwd=repo)
    unexpected = _status_paths(status) - (allowed_dirty or set())
    if unexpected:
        sample = "\n".join(sorted(unexpected)[:8])
        raise GitHubPublishError(
            "The GitHub checkout has other uncommitted changes. Commit or stash them first; "
            "Smart Drive Organizer will not mix unrelated files into a publish.\n\n" + sample
        )


def _check_remote_sync(repo: Path, branch: str) -> bool:
    remote_ref = f"refs/heads/{branch}"
    ls_remote = _git(["ls-remote", "--heads", "origin", remote_ref], cwd=repo, timeout=60)
    if ls_remote.returncode != 0:
        detail = (ls_remote.stderr or ls_remote.stdout or "Could not contact GitHub.").strip()
        raise GitHubPublishError(f"Could not check the GitHub branch. Check your internet connection and GitHub sign-in.\n{detail}")
    remote_has_branch = bool(ls_remote.stdout.strip())
    if remote_has_branch:
        fetch = _git(["fetch", "origin", branch], cwd=repo, timeout=90)
        if fetch.returncode != 0:
            raise GitHubPublishError((fetch.stderr or fetch.stdout or "Git fetch failed.").strip())
        counts = _git_output(["rev-list", "--left-right", "--count", f"HEAD...origin/{branch}"], cwd=repo)
        try:
            ahead, behind = [int(part) for part in counts.split()]
        except (ValueError, TypeError):
            raise GitHubPublishError("Could not compare your local branch with GitHub.")
        if ahead or behind:
            raise GitHubPublishError(
                f"Your local branch and GitHub are not synchronized (local-only commits: {ahead}; "
                f"GitHub-only commits: {behind}). Reconcile them first. Nothing new was pushed."
            )
    return remote_has_branch


def _commit_identity(repo: Path, author_name: str, author_email: str) -> tuple[str, str]:
    try:
        configured_name = _git_output(["config", "user.name"], cwd=repo)
    except GitHubPublishError:
        configured_name = ""
    try:
        configured_email = _git_output(["config", "user.email"], cwd=repo)
    except GitHubPublishError:
        configured_email = ""
    name = author_name.strip() or configured_name
    email = author_email.strip() or configured_email
    if not name or not email:
        raise GitHubPublishError("Enter your Git commit name and email in the publishing settings, or configure them in Git.")
    return name, email


def _commit_and_push(
    repo: Path, branch: str, remote_has_branch: bool, relative_paths: list[str],
    commit_message: str, author_name: str, author_email: str,
) -> dict[str, Any]:
    args = ["-c", f"user.name={author_name}", "-c", f"user.email={author_email}", "commit", "--only", "-m", commit_message, "--", *relative_paths]
    commit = _git(args, cwd=repo, timeout=90)
    if commit.returncode != 0:
        raise GitHubPublishError((commit.stderr or commit.stdout or "Git commit failed.").strip())
    push_args = ["push"] + ([] if remote_has_branch else ["--set-upstream"]) + ["origin", branch]
    push = _git(push_args, cwd=repo, timeout=180)
    if push.returncode != 0:
        detail = (push.stderr or push.stdout or "Git push failed.").strip()
        return {
            "status": "committed_not_pushed",
            "message": "The changes were committed locally, but GitHub did not accept the push. The local commit is safe.\n" + detail,
            "repository": str(repo), "branch": branch,
            "commit": commit.stdout.strip().splitlines()[-1] if commit.stdout.strip() else "",
            "files": relative_paths,
        }
    return {
        "status": "pushed", "message": "The approved update was committed and pushed to GitHub successfully.",
        "repository": str(repo), "branch": branch,
        "commit": commit.stdout.strip().splitlines()[-1] if commit.stdout.strip() else "",
        "files": relative_paths,
    }


def publish_topic_rules_to_github(
    repository_path: str | Path, rules: list[dict[str, Any]],
    author_name: str = "", author_email: str = "",
) -> dict[str, Any]:
    """Commit and push only config/published_topic_rules.json to a GitHub remote."""
    info = resolve_repository_reference(repository_path)
    repo = Path(info["path"])
    branch = info["branch"]
    relative = PUBLISHED_RULES_RELATIVE_PATH.as_posix()
    _assert_clean_repository(repo, allowed_dirty={relative})
    remote_has_branch = _check_remote_sync(repo, branch)
    name, email = _commit_identity(repo, author_name, author_email)

    payload = build_published_rules_payload(rules)
    target = repo / PUBLISHED_RULES_RELATIVE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status = _git_output(["status", "--porcelain", "--untracked-files=all"], cwd=repo)
    unexpected = _status_paths(status) - {relative}
    if unexpected:
        raise GitHubPublishError("Another repository file changed while preparing the publish. Nothing was pushed.")
    add = _git(["add", "--", relative], cwd=repo)
    if add.returncode != 0:
        raise GitHubPublishError((add.stderr or add.stdout or "Could not stage the topic rules.").strip())
    changed = _git(["diff", "--cached", "--quiet", "--", relative], cwd=repo)
    if changed.returncode == 0:
        return {"status": "unchanged", "message": "The GitHub repository already has these keyword rules.", "repository": str(repo), "branch": branch, "file": relative}
    if changed.returncode != 1:
        raise GitHubPublishError("Git could not inspect the staged rules file.")

    result = _commit_and_push(
        repo, branch, remote_has_branch, [relative], "Update Smart Drive Organizer keyword rules", name, email
    )
    result["file"] = relative
    return result


def project_source_root() -> Path:
    """Return the source tree containing run.py and smart_drive_organizer/."""
    return Path(__file__).resolve().parent.parent


def collect_publishable_source_files(source_root: Optional[str | Path] = None) -> dict[str, Path]:
    """Collect only the explicit application-source allowlist, never user data or arbitrary files."""
    root = Path(source_root or project_source_root()).expanduser().resolve()
    if not root.is_dir():
        raise GitHubPublishError("The application source folder could not be found. Source publishing is unavailable in this build.")
    files: dict[str, Path] = {}
    for pattern in PUBLISHABLE_SOURCE_PATTERNS:
        for candidate in root.glob(pattern):
            if not candidate.is_file() or candidate.is_symlink():
                continue
            relative = candidate.relative_to(root).as_posix()
            if relative.startswith((".git/", "__pycache__/")) or "/__pycache__/" in relative:
                continue
            files[relative] = candidate
    if not files:
        raise GitHubPublishError("No approved application source files were found to publish.")
    return dict(sorted(files.items()))


def _check_source_for_secrets(path: Path, content: bytes) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            raise GitHubPublishError(
                f"Publishing stopped because a possible credential or private key was detected in {path}. "
                "Remove the secret from the source file before publishing."
            )


def _source_change_plan(repo: Path, source_root: Optional[str | Path] = None) -> dict[str, list[str]]:
    source_files = collect_publishable_source_files(source_root)
    added: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    for relative, source in source_files.items():
        content = source.read_bytes()
        _check_source_for_secrets(relative, content)
        target = repo / relative
        if not target.exists():
            added.append(relative)
        elif not target.is_file() or target.read_bytes() != content:
            updated.append(relative)
        else:
            unchanged.append(relative)
    return {"added": added, "updated": updated, "unchanged": unchanged}


def preview_application_update_to_github(
    repository_reference: str | Path, source_root: Optional[str | Path] = None,
) -> dict[str, Any]:
    """Preview allowed source files before an explicit source-code publish."""
    info = resolve_repository_reference(repository_reference)
    repo = Path(info["path"])
    _assert_clean_repository(repo)
    _check_remote_sync(repo, info["branch"])
    plan = _source_change_plan(repo, source_root)
    return {**info, **plan, "total_changes": len(plan["added"]) + len(plan["updated"])}


def publish_application_update_to_github(
    repository_reference: str | Path, source_root: Optional[str | Path] = None,
    author_name: str = "", author_email: str = "", commit_message: str = "Update Smart Drive Organizer application",
) -> dict[str, Any]:
    """Publish only allowlisted application source files after the user approves a preview."""
    info = resolve_repository_reference(repository_reference)
    repo = Path(info["path"])
    branch = info["branch"]
    _assert_clean_repository(repo)
    remote_has_branch = _check_remote_sync(repo, branch)
    name, email = _commit_identity(repo, author_name, author_email)
    plan = _source_change_plan(repo, source_root)
    changed_paths = sorted(plan["added"] + plan["updated"])
    if not changed_paths:
        return {"status": "unchanged", "message": "The GitHub repository already contains the current approved application source files.", "repository": str(repo), "branch": branch, "files": []}

    source_files = collect_publishable_source_files(source_root)
    for relative in changed_paths:
        source = source_files[relative]
        content = source.read_bytes()
        _check_source_for_secrets(relative, content)
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    add = _git(["add", "--", *changed_paths], cwd=repo, timeout=60)
    if add.returncode != 0:
        raise GitHubPublishError((add.stderr or add.stdout or "Could not stage approved source files.").strip())
    staged_status = _git_output(["status", "--porcelain", "--untracked-files=all"], cwd=repo)
    unexpected = _status_paths(staged_status) - set(changed_paths)
    if unexpected:
        raise GitHubPublishError(
            "A repository file outside the approved source list changed while preparing the update. Nothing was committed.\n"
            + "\n".join(sorted(unexpected)[:8])
        )
    changed = _git(["diff", "--cached", "--quiet", "--", *changed_paths], cwd=repo)
    if changed.returncode == 0:
        return {"status": "unchanged", "message": "There are no application source changes to publish.", "repository": str(repo), "branch": branch, "files": []}
    if changed.returncode != 1:
        raise GitHubPublishError("Git could not inspect the staged application source update.")
    result = _commit_and_push(
        repo, branch, remote_has_branch, changed_paths,
        commit_message.strip() or "Update Smart Drive Organizer application", name, email,
    )
    result["added"] = plan["added"]
    result["updated"] = plan["updated"]
    return result
