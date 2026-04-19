import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import ttk
from typing import Callable, Optional

from gui.utils import fmt_dt


class DealsTab(ttk.Frame):
    _COLUMNS = (
        "status",
        "discovered",
        "published",
        "monitor",
        "feed",
        "price",
        "title",
    )
    _HEADINGS = {
        "status": "Status",
        "discovered": "Discovered",
        "published": "Published",
        "monitor": "Monitor",
        "feed": "Feed",
        "price": "Price",
        "title": "Title",
    }
    _WIDTHS = {
        "status": 70,
        "discovered": 130,
        "published": 130,
        "monitor": 120,
        "feed": 110,
        "price": 70,
        "title": 370,
    }

    def __init__(self, parent: ttk.Notebook, on_check_now: Callable) -> None:
        super().__init__(parent)
        self._on_check_now = on_check_now
        self._links: dict[str, str] = {}
        self._build()

    def _build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=(6, 0))

        self._status_var = tk.StringVar(value="No checks run yet.")
        ttk.Label(
            toolbar, textvariable=self._status_var, foreground="#555"
        ).pack(side="left")
        ttk.Button(toolbar, text="Clear", command=self._clear).pack(
            side="right", padx=(4, 0)
        )
        ttk.Button(
            toolbar, text="⚡ Check Now", command=self._on_check_now
        ).pack(side="right")

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=6, pady=6)

        self._tree = ttk.Treeview(
            frame, columns=self._COLUMNS, show="headings", selectmode="browse"
        )
        for col in self._COLUMNS:
            self._tree.heading(col, text=self._HEADINGS[col])
            self._tree.column(
                col, width=self._WIDTHS[col], stretch=(col == "title")
            )

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.tag_configure("new", background="#e6ffe6")  # green tint
        self._tree.tag_configure(
            "historical", background="#fffbe6"
        )  # yellow tint
        self._tree.bind("<Double-1>", self._open_link)

        ttk.Label(
            self,
            text="Double-click a row to open in browser",
            foreground="#888",
        ).pack(pady=(0, 4))

    def add_deal(
        self,
        monitor_name: str,
        feed_name: str,
        entry: dict,
        price: Optional[float],
        discovered_at=None,
        is_new: bool = True,
    ) -> None:
        discovered_str = fmt_dt(
            discovered_at if discovered_at is not None else datetime.now()
        )
        published_str = fmt_dt(entry.get("published", ""))
        price_str = f"${price:.2f}" if price is not None else "?"
        status_label = "🆕 New" if is_new else "📦 Historical"
        tag = "new" if is_new else "historical"
        iid = self._tree.insert(
            "",
            0,  # newest at top
            values=(
                status_label,
                discovered_str,
                published_str,
                monitor_name,
                feed_name,
                price_str,
                entry["title"],
            ),
            tags=(tag,),
        )
        self._links[iid] = entry["link"]

    def set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    def _open_link(self, _event) -> None:
        item = self._tree.focus()
        if item and item in self._links:
            webbrowser.open(self._links[item])

    def clear(self) -> None:
        self._tree.delete(*self._tree.get_children())
        self._links.clear()

    def _clear(self) -> None:
        self.clear()
