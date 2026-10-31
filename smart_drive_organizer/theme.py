from __future__ import annotations

from typing import Any

LIGHT = {
    "bg": "#F4F4F5",
    "card": "#FFFFFF",
    "ink": "#101010",
    "black": "#101010",
    "white": "#FFFFFF",
    "red": "#D71920",
    "muted": "#737373",
    "border": "#E4E4E7",
    "hover": "#F1F1F1",
    "disabled": "#E5E5E5",
    "trough": "#E5E5E5",
    "badge": "#FEE2E2",
}
DARK = {
    "bg": "#151515",
    "card": "#242424",
    "ink": "#F4F4F5",
    "black": "#090909",
    "white": "#FFFFFF",
    "red": "#D71920",
    "muted": "#A1A1AA",
    "border": "#3F3F46",
    "hover": "#303030",
    "disabled": "#484848",
    "trough": "#3F3F46",
    "badge": "#3A191B",
}


def palette_for(parent: Any) -> dict[str, str]:
    """Return the application's persisted palette for any child dialog."""
    return DARK if getattr(parent, "theme_name", "light") == "dark" else LIGHT
