from __future__ import annotations

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

