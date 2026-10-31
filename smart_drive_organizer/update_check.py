from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

RELEASE_API_URL = "https://api.github.com/repos/T3ND41/SmartDriveOrganizer_RepoReady_v0.3.7/releases/latest"
RELEASE_PAGE_PREFIX = "https://github.com/T3ND41/SmartDriveOrganizer_RepoReady_v0.3.7/releases/tag/"


def _version_parts(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?", str(value).strip(), re.IGNORECASE)
    if not match:
        raise ValueError(f"Unrecognised application version: {value!r}")
    return tuple(int(part) for part in match.groups())


def check_latest_release(current_version: str, timeout: float = 8.0) -> dict[str, object]:
    """Return the latest official release metadata without downloading or installing it."""
    _version_parts(current_version)
    request = Request(
        RELEASE_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SmartDriveOrganizer-Desktop",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        release = json.loads(response.read().decode("utf-8"))

    tag = str(release.get("tag_name", "")).strip()
    latest_parts = _version_parts(tag)
    release_url = str(release.get("html_url", "")).strip()
    parsed_url = urlsplit(release_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.netloc.casefold() != "github.com"
        or not release_url.startswith(RELEASE_PAGE_PREFIX)
    ):
        raise ValueError("GitHub returned an unexpected release page URL; it was not opened.")

    current_parts = _version_parts(current_version)
    return {
        "current_version": str(current_version),
        "latest_version": tag.removeprefix("v"),
        "update_available": latest_parts > current_parts,
        "release_url": release_url,
        "release_name": str(release.get("name") or tag),
        "published_at": str(release.get("published_at") or ""),
    }
