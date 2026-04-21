import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from gui.utils import attach_context_menu


class MonitorsTab(ttk.Frame):
    _COLUMNS = ("name", "terms", "max_price", "feeds", "enabled")
    _HEADINGS = {
        "name": "Name",
        "terms": "Terms",
        "max_price": "Max Price",
        "feeds": "Feeds",
        "enabled": "Enabled",
    }
    _WIDTHS = {
        "name": 140,
        "terms": 240,
        "max_price": 90,
        "feeds": 220,
        "enabled": 70,
    }

    def __init__(
        self,
        parent: ttk.Notebook,
        get_config: Callable,
        save_config: Callable,
    ) -> None:
        super().__init__(parent)
        self._get_config = get_config
        self._save_config = save_config
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=(6, 0))
        ttk.Button(toolbar, text="Add Monitor", command=self._add).pack(
            side="left"
        )
        ttk.Button(toolbar, text="Remove", command=self._remove).pack(
            side="left", padx=4
        )
        ttk.Button(toolbar, text="Edit", command=self._edit).pack(side="left")
        ttk.Button(
            toolbar, text="Toggle Enable/Disable", command=self._toggle
        ).pack(side="left", padx=(4, 0))

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=6, pady=6)

        self._tree = ttk.Treeview(
            frame, columns=self._COLUMNS, show="headings", selectmode="browse"
        )
        for col in self._COLUMNS:
            self._tree.heading(col, text=self._HEADINGS[col])
            self._tree.column(
                col, width=self._WIDTHS[col], stretch=(col == "terms")
            )

        self._tree.tag_configure("enabled", foreground="#1a6b1a")
        self._tree.tag_configure("disabled", foreground="#999999")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        attach_context_menu(
            self._tree,
            [
                ("✏️ Edit", self._edit),
                ("🔄 Toggle Enable/Disable", self._toggle),
                ("📋 Copy Name", self._ctx_copy_name),
                ("📋 Copy Terms", self._ctx_copy_terms),
                (None, None),
                ("🗑 Remove", self._remove),
            ],
        )

    def refresh(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for m in self._get_config()["monitors"]:
            price_str = (
                f"${m['max_price']:.2f}"
                if m.get("max_price") is not None
                else "any"
            )
            enabled = m.get("enabled", True)
            self._tree.insert(
                "",
                "end",
                values=(
                    m["name"],
                    ", ".join(m.get("terms", [])),
                    price_str,
                    ", ".join(m.get("feeds", [])) or "(all feeds)",
                    "Yes" if enabled else "No",
                ),
                tags=("enabled" if enabled else "disabled",),
            )

    def _selected_name(self) -> str | None:
        sel = self._tree.focus()
        if not sel:
            return None
        return self._tree.item(sel)["values"][0]

    def _add(self) -> None:
        from gui.dialogs import AddMonitorDialog

        config = self._get_config()
        dlg = AddMonitorDialog(
            self, feed_names=[f["name"] for f in config["feeds"]]
        )
        self.wait_window(dlg)
        if not dlg.result:
            return
        name, terms, max_price, feeds = dlg.result
        monitor: dict = {
            "name": name,
            "terms": terms,
            "feeds": feeds,
            "enabled": True,
        }
        if max_price is not None:
            monitor["max_price"] = max_price
        config["monitors"].append(monitor)
        self._save_config(config)

    def _edit(self) -> None:
        from gui.dialogs import AddMonitorDialog

        name = self._selected_name()
        if not name:
            return
        config = self._get_config()
        monitor = next(
            (m for m in config["monitors"] if m["name"] == name), None
        )
        if not monitor:
            return
        dlg = AddMonitorDialog(
            self,
            feed_names=[f["name"] for f in config["feeds"]],
            initial=monitor,
        )
        self.wait_window(dlg)
        if not dlg.result:
            return
        new_name, terms, max_price, feeds = dlg.result
        for m in config["monitors"]:
            if m["name"] == name:
                m["name"] = new_name
                m["terms"] = terms
                m["feeds"] = feeds
                if max_price is not None:
                    m["max_price"] = max_price
                elif "max_price" in m:
                    del m["max_price"]
                break
        self._save_config(config)

    def _remove(self) -> None:
        name = self._selected_name()
        if not name:
            return
        if not messagebox.askyesno(
            "Remove Monitor", f"Remove monitor '{name}'?"
        ):
            return
        config = self._get_config()
        config["monitors"] = [
            m for m in config["monitors"] if m["name"] != name
        ]
        self._save_config(config)

    def _ctx_copy_name(self) -> None:
        name = self._selected_name()
        if name:
            self.clipboard_clear()
            self.clipboard_append(name)

    def _ctx_copy_terms(self) -> None:
        sel = self._tree.focus()
        if sel:
            terms = self._tree.item(sel)["values"][1]  # "terms" column
            self.clipboard_clear()
            self.clipboard_append(str(terms))

    def _toggle(self) -> None:
        name = self._selected_name()
        if not name:
            return
        config = self._get_config()
        for m in config["monitors"]:
            if m["name"] == name:
                m["enabled"] = not m.get("enabled", True)
                break
        self._save_config(config)
