from __future__ import annotations

from typing import Any

LIGHT = {
    "bg": "#F4F4F5", "card": "#FFFFFF", "ink": "#101010", "black": "#101010",
    "white": "#FFFFFF", "red": "#D71920", "muted": "#737373", "border": "#E4E4E7",
    "hover": "#F1F1F1", "disabled": "#E5E5E5", "trough": "#E5E5E5", "badge": "#FEE2E2",
}
REDLINE = {
    "bg": "#101010", "card": "#191919", "ink": "#FFFFFF", "black": "#000000",
    "white": "#FFFFFF", "red": "#D71920", "muted": "#C4C4C4", "border": "#4B2527",
    "hover": "#292929", "disabled": "#5A292B", "trough": "#3D1719", "badge": "#351316",
}
DARK = {
    "bg": "#151515", "card": "#242424", "ink": "#F4F4F5", "black": "#090909",
    "white": "#FFFFFF", "red": "#D71920", "muted": "#A1A1AA", "border": "#3F3F46",
    "hover": "#303030", "disabled": "#484848", "trough": "#3F3F46", "badge": "#3A191B",
}


def palette_for(parent: Any) -> dict[str, str]:
    """Return the application's approved persisted brand palette."""
    selected = getattr(parent, "theme_name", "light")
    if selected == "dark":
        return DARK
    if selected == "redline":
        return REDLINE
    return LIGHT


def apply_dialog_theme(widget: Any, parent: Any) -> dict[str, str]:
    """Apply the approved brand palette and shared button styles to a dialog."""
    import tkinter.ttk as ttk

    palette = palette_for(parent)
    try:
        style = ttk.Style(widget)
        style.theme_use("clam")
        style.configure("TFrame", background=palette["bg"])
        style.configure("TLabel", background=palette["bg"], foreground=palette["ink"], font=("Segoe UI", 9))
        style.configure("TLabelframe", background=palette["card"], bordercolor=palette["border"])
        style.configure("TLabelframe.Label", background=palette["card"], foreground=palette["ink"], font=("Segoe UI", 9, "bold"))
        style.configure("TButton", background=palette["card"], foreground=palette["ink"], padding=(10, 7), font=("Segoe UI", 9))
        style.map("TButton", background=[("active", palette["hover"]), ("disabled", palette["disabled"])],
                  foreground=[("disabled", palette["muted"])])
        style.configure("Primary.TButton", background=palette["red"], foreground=palette["white"], padding=(12, 8), font=("Segoe UI", 9, "bold"))
        style.map("Primary.TButton", background=[("active", palette["red"]), ("disabled", palette["disabled"])],
                  foreground=[("disabled", palette["white"])])
        style.configure("Secondary.TButton", background=palette["bg"], foreground=palette["ink"], padding=(10, 7))
        style.map("Secondary.TButton", background=[("active", palette["hover"])])
        style.configure("Dark.TButton", background=palette["black"], foreground=palette["white"], padding=(12, 8), font=("Segoe UI", 9, "bold"))
        style.map("Dark.TButton", background=[("active", palette["hover"])])
        style.configure("TEntry", fieldbackground=palette["card"], foreground=palette["ink"])
        style.configure("TCombobox", fieldbackground=palette["card"], foreground=palette["ink"])
        style.configure("TCheckbutton", background=palette["bg"], foreground=palette["ink"])
        style.map("TCheckbutton", background=[("active", palette["bg"])])
        style.configure("TRadiobutton", background=palette["bg"], foreground=palette["ink"])
        style.map("TRadiobutton", background=[("active", palette["bg"])])
        style.configure("TNotebook", background=palette["bg"], bordercolor=palette["border"])
        style.configure("TNotebook.Tab", background=palette["card"], foreground=palette["ink"], padding=(10, 6))
        style.map("TNotebook.Tab", background=[("selected", palette["red"])],
                  foreground=[("selected", palette["white"])])
        style.configure("Treeview", background=palette["card"], fieldbackground=palette["card"],
                        foreground=palette["ink"], rowheight=28)
        style.configure("Treeview.Heading", background=palette["black"], foreground=palette["white"],
                        font=("Segoe UI", 9, "bold"), padding=(8, 7))
        style.map("Treeview.Heading", background=[("active", palette["red"])])
        style.configure("Red.Horizontal.TProgressbar", troughcolor=palette["trough"], background=palette["red"])
    except Exception:
        pass
    try:
        widget.configure(bg=palette["bg"])
    except Exception:
        pass
    return palette
