from __future__ import annotations

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.text import Text


BRAND_NAME = "NSU AUDIT TOOL"
BRAND_ACCENT = "#c15f3c"


def header_lines(username: str | None) -> list[str]:
    if username:
        return [f"  {BRAND_NAME}", f"  Welcome, {username}"]
    return [f"  {BRAND_NAME}", "  Not logged in"]


def header_text(username: str | None) -> Text:
    """Rich-renderable header content (used inside the box header)."""
    lines = header_lines(username)
    t = Text("\n".join(lines))
    # Accent just the brand name portion on the first line.
    t.stylize(BRAND_ACCENT, 2, 2 + len(BRAND_NAME))
    return t


def header_panel(username: str | None) -> Panel:
    """TUI header: border fits content width/height (not full terminal width)."""
    title = Text(BRAND_NAME, style=f"bold {BRAND_ACCENT}")
    if username:
        sub = Text.assemble("Welcome, ", (username, ""))
    else:
        sub = Text("Not logged in", style="dim")
    return Panel(
        Group(title, sub),
        border_style=BRAND_ACCENT,
        box=box.DOUBLE,
        expand=False,
        padding=(0, 1),
    )

