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
REDLINE = {
    "bg": "#101010",
    "card": "#191919",
    "ink": "#FFFFFF",
    "black": "#000000",
    "white": "#FFFFFF",
    "red": "#D71920",
    "muted": "#C4C4C4",
    "border": "#4B2527",
    "hover": "#292929",
    "disabled": "#5A292B",
    "trough": "#3D1719",
    "badge": "#351316",
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
    selected = getattr(parent, "theme_name", "light")
    if selected == "dark":
        return DARK
    if selected == "redline":
        return REDLINE
    return LIGHT


def apply_dialog_theme(widget: Any, parent: Any) -> dict[str, str]:
    """Apply the selected palette to standard ttk widgets in secondary dialogs."""
    palette = palette_for(parent)
    style = ttk_style = None
    try:
        import tkinter.ttk as ttk
        style = ttk.Style(widget)
        style.theme_use("clam")
        style.configure("TFrame", background=palette["bg"])
        style.configure("TLabel", background=palette["bg"], foreground=palette["ink"], font=("Segoe UI", 9))
        style.configure("TLabelframe", background=palette["bg"], bordercolor=palette["border"])
        style.configure("TLabelframe.Label", background=palette["bg"], foreground=palette["ink"], font=("Segoe UI", 9, "bold"))
        style.configure("TButton", background=palette["card"], foreground=palette["ink"], padding=(9, 7))
        style.map("TButton", background=[("active", palette["hover"]), ("disabled", palette["disabled"])])
        style.configure("TEntry", fieldbackground=palette["card"], foreground=palette["ink"])
        style.configure("TCombobox", fieldbackground=palette["card"], foreground=palette["ink"])
        style.configure("TCheckbutton", background=palette["bg"], foreground=palette["ink"])
        style.configure("TRadiobutton", background=palette["bg"], foreground=palette["ink"])
        style.configure("Treeview", background=palette["card"], fieldbackground=palette["card"], foreground=palette["ink"], rowheight=27)
        style.configure("Treeview.Heading", background=palette["black"], foreground=palette["white"])
    except Exception:
        pass
    try:
        widget.configure(bg=palette["bg"])
    except Exception:
        pass
    return palette
