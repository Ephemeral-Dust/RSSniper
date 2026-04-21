"""Shared GUI utility helpers."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime, timezone
from tkinter import ttk
from typing import Callable, Union


def apply_dialog_icon(dialog: tk.Toplevel) -> None:
    """Apply the app icon to a Toplevel dialog window."""
    try:
        from paths import get_asset_dir

        ico = get_asset_dir() / "icons" / "icon.ico"
        if ico.exists():
            dialog.iconbitmap(str(ico))
    except Exception:
        pass


def attach_context_menu(
    tree: ttk.Treeview,
    items: list[tuple[str | None, Callable | None]],
    *,
    menu_kw: dict | None = None,
) -> None:
    """Attach a right-click context menu to a Treeview.

    ``items`` is a list of (label, callback) pairs.  Pass ``(None, None)``
    for a separator.  The callback receives the selected row iid as its
    only argument; if no row is under the cursor the menu is not shown.

    ``menu_kw`` is forwarded to ``tk.Menu`` (e.g. dark-theme colours).
    """
    kw = menu_kw or {}
    menu = tk.Menu(tree, tearoff=False, **kw)
    for label, cmd in items:
        if label is None:
            menu.add_separator()
        else:
            menu.add_command(label=label, command=lambda c=cmd: c())

    def _show(event: tk.Event) -> None:
        # Select the row under cursor first so callbacks have a focused item.
        iid = tree.identify_row(event.y)
        if not iid:
            return
        tree.focus(iid)
        tree.selection_set(iid)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    tree.bind("<Button-3>", _show)


def fmt_dt(value: Union[str, datetime, None]) -> str:
    """Convert a date value to a human-readable local-time string.

    Accepts:
    - An RFC 2822 string (e.g. feedparser's ``entry.published``)
    - A ``datetime`` object (naive assumed UTC, aware converted)
    - ``None`` / empty string → returns ``""``

    Returns strings like ``"19/04/2026 4:00 PM"``.
    """
    if not value:
        return ""

    dt: datetime | None = None

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        # Try RFC 2822 (feedparser published strings)
        try:
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(value)
        except Exception:
            pass

        # Fallback: ISO 8601
        if dt is None:
            for fmt in (
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ",
            ):
                try:
                    dt = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    continue

        # SQLite stores timestamps as UTC without timezone info;
        # attach UTC so conversion to local time works correctly.
        if dt is None:
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ):
                try:
                    dt = datetime.strptime(value, fmt).replace(
                        tzinfo=timezone.utc
                    )
                    break
                except ValueError:
                    continue

    if dt is None:
        return value if isinstance(value, str) else ""

    # Convert to local time
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    # else leave naive (assumed already local)

    # Build date/time string, stripping leading zeros portably (Windows-safe)
    day = str(dt.day)
    month = dt.strftime("%m")
    year = dt.strftime("%Y")
    hour = str(dt.hour % 12 or 12)
    minute = dt.strftime("%M")
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{day}/{month}/{year} {hour}:{minute} {ampm}"
