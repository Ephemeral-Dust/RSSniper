import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Callable

from gui.utils import attach_context_menu


class FeedsTab(ttk.Frame):
    _COLUMNS = ("name", "url", "type")
    _HEADINGS = {"name": "Name", "url": "URL", "type": "Type"}
    _WIDTHS = {"name": 160, "url": 520, "type": 80}

    def __init__(
        self,
        parent: ttk.Notebook,
        get_config: Callable,
        save_config: Callable,
        get_conn: Callable = None,
    ) -> None:
        super().__init__(parent)
        self._get_config = get_config
        self._save_config = save_config
        self._get_conn = get_conn
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=(6, 0))
        ttk.Button(toolbar, text="Add Feed", command=self._add).pack(
            side="left"
        )
        ttk.Button(toolbar, text="Remove", command=self._remove).pack(
            side="left", padx=4
        )
        ttk.Button(toolbar, text="Edit", command=self._edit).pack(side="left")
        ttk.Button(toolbar, text="Preview Feed", command=self._preview).pack(
            side="left", padx=(4, 0)
        )

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=6, pady=6)

        self._tree = ttk.Treeview(
            frame, columns=self._COLUMNS, show="headings", selectmode="browse"
        )
        for col in self._COLUMNS:
            self._tree.heading(col, text=self._HEADINGS[col])
            self._tree.column(
                col, width=self._WIDTHS[col], stretch=(col == "url")
            )

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.bind("<Double-1>", lambda _e: self._preview())

        attach_context_menu(
            self._tree,
            [
                ("🔍 Preview Feed", self._preview),
                ("✏️ Edit", self._edit),
                (None, None),
                ("🌐 Open Feed URL in Browser", self._ctx_open_url),
                ("🔗 Copy URL", self._ctx_copy_url),
                ("📋 Copy Name", self._ctx_copy_name),
                (None, None),
                ("🗑 Remove", self._remove),
            ],
        )

        ttk.Label(
            self,
            text='Double-click a feed or press "Preview Feed" to browse its latest items.',
            foreground="#888",
        ).pack(pady=(0, 4))

    def refresh(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for f in self._get_config()["feeds"]:
            self._tree.insert(
                "", "end", values=(f["name"], f["url"], f.get("type", "rss"))
            )

    def _selected_feed_cfg(self) -> dict | None:
        sel = self._tree.focus()
        if not sel:
            return None
        values = self._tree.item(sel)["values"]
        return {"name": values[0], "url": values[1], "type": values[2]}

    def _add(self) -> None:
        from gui.dialogs import AddFeedDialog

        dlg = AddFeedDialog(self)
        self.wait_window(dlg)
        if not dlg.result:
            return
        name, url, feed_type = dlg.result
        config = self._get_config()
        if any(f["name"] == name for f in config["feeds"]):
            messagebox.showerror("Duplicate", f"Feed '{name}' already exists.")
            return
        config["feeds"].append({"name": name, "url": url, "type": feed_type})
        self._save_config(config)

    def _edit(self) -> None:
        from gui.dialogs import AddFeedDialog

        feed_cfg = self._selected_feed_cfg()
        if not feed_cfg:
            return
        dlg = AddFeedDialog(self, initial=feed_cfg)
        self.wait_window(dlg)
        if not dlg.result:
            return
        new_name, new_url, new_type = dlg.result
        old_name = feed_cfg["name"]
        config = self._get_config()
        for f in config["feeds"]:
            if f["name"] == old_name:
                f["name"] = new_name
                f["url"] = new_url
                f["type"] = new_type
                break
        if new_name != old_name:
            for m in config["monitors"]:
                m["feeds"] = [
                    new_name if fn == old_name else fn
                    for fn in m.get("feeds", [])
                ]
        self._save_config(config)

    def _remove(self) -> None:
        feed_cfg = self._selected_feed_cfg()
        if not feed_cfg:
            return
        if not messagebox.askyesno(
            "Remove Feed", f"Remove '{feed_cfg['name']}'?"
        ):
            return
        config = self._get_config()
        config["feeds"] = [
            f for f in config["feeds"] if f["name"] != feed_cfg["name"]
        ]
        self._save_config(config)

    def _ctx_open_url(self) -> None:
        feed_cfg = self._selected_feed_cfg()
        if feed_cfg:
            webbrowser.open(feed_cfg["url"])

    def _ctx_copy_url(self) -> None:
        feed_cfg = self._selected_feed_cfg()
        if feed_cfg:
            self.clipboard_clear()
            self.clipboard_append(feed_cfg["url"])

    def _ctx_copy_name(self) -> None:
        feed_cfg = self._selected_feed_cfg()
        if feed_cfg:
            self.clipboard_clear()
            self.clipboard_append(feed_cfg["name"])

    def _preview(self) -> None:
        from gui.dialogs import FeedPreviewDialog

        feed_cfg = self._selected_feed_cfg()
        if not feed_cfg:
            messagebox.showinfo("Preview Feed", "Select a feed first.")
            return
        user_agent = self._get_config().get(
            "user_agent", "RedditDealWatcher/1.0"
        )
        conn = self._get_conn() if self._get_conn else None
        FeedPreviewDialog(self, feed_cfg, user_agent, conn=conn)
