import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Callable

from gui.utils import (
    attach_context_menu,
    PATTERN_NONE_LABEL,
    PATTERN_BUILTIN_SEP,
    PATTERN_CUSTOM_SEP,
)


class FeedsTab(ttk.Frame):
    _COLUMNS = ("name", "url", "pattern")
    _HEADINGS = {
        "name": "Name",
        "url": "URL",
        "pattern": "Match Pattern",
    }
    _WIDTHS = {"name": 150, "url": 430, "pattern": 200}
    _NONE_LABEL = PATTERN_NONE_LABEL
    _BUILTIN_SEP = PATTERN_BUILTIN_SEP
    _CUSTOM_SEP = PATTERN_CUSTOM_SEP

    def __init__(
        self,
        parent: ttk.Notebook,
        get_config: Callable,
        save_config: Callable,
        get_conn: Callable = None,
        on_feed_pattern_change: Callable = None,
        on_check_now: Callable = None,
        on_minimize: Callable = None,
    ) -> None:
        super().__init__(parent)
        self._get_config = get_config
        self._save_config = save_config
        self._get_conn = get_conn
        self._on_feed_pattern_change = on_feed_pattern_change
        self._on_check_now = on_check_now or (lambda: None)
        self._on_minimize = on_minimize or (lambda: None)
        self._pattern_popup: ttk.Combobox | None = None
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
        ttk.Button(toolbar, text="⬇ Tray", command=self._on_minimize).pack(
            side="right"
        )
        ttk.Button(
            toolbar, text="⚡ Check Now", command=self._on_check_now
        ).pack(side="right", padx=(0, 4))

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
        self._tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self._tree.bind("<Motion>", self._on_tree_motion)

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
        self._close_pattern_popup()
        self._tree.delete(*self._tree.get_children())
        all_presets = self._all_presets_map()
        # Reverse map: regex → preset name, for display lookup
        preset_by_regex = {v: k for k, v in all_presets.items()}
        for f in self._get_config()["feeds"]:
            raw = f.get("match_pattern", "")
            if not raw:
                display = "Full text (default)"
            else:
                display = preset_by_regex.get(raw, raw)
            self._tree.insert(
                "",
                "end",
                values=(
                    f["name"],
                    f["url"],
                    f"{display} \u25be",
                ),
            )

    def _selected_feed_cfg(self) -> dict | None:
        sel = self._tree.focus()
        if not sel:
            return None
        values = self._tree.item(sel)["values"]
        name = values[0]
        # Return the full config dict so all fields (incl. match_pattern) are available.
        for f in self._get_config()["feeds"]:
            if f["name"] == name:
                return f
        return {"name": values[0], "url": values[1]}

    def _add(self) -> None:
        from gui.dialogs import AddFeedDialog

        dlg = AddFeedDialog(
            self,
            get_config=self._get_config,
            save_config=self._save_config,
        )
        self.wait_window(dlg)
        if not dlg.result:
            return
        name = dlg.result["name"]
        url = dlg.result["url"]
        config = self._get_config()
        if any(f["name"] == name for f in config["feeds"]):
            messagebox.showerror("Duplicate", f"Feed '{name}' already exists.")
            return
        entry: dict = {"name": name, "url": url}
        if dlg.result.get("match_pattern"):
            entry["match_pattern"] = dlg.result["match_pattern"]
        config["feeds"].append(entry)
        self._save_config(config)

    def _edit(self) -> None:
        from gui.dialogs import AddFeedDialog

        feed_cfg = self._selected_feed_cfg()
        if not feed_cfg:
            return
        dlg = AddFeedDialog(
            self,
            initial=feed_cfg,
            get_config=self._get_config,
            save_config=self._save_config,
        )
        self.wait_window(dlg)
        if not dlg.result:
            return
        new_name = dlg.result["name"]
        new_url = dlg.result["url"]
        new_pattern = dlg.result.get("match_pattern", "")
        old_pattern = feed_cfg.get("match_pattern", "")
        old_name = feed_cfg["name"]
        config = self._get_config()
        # Guard: if the name changed, make sure the new name isn't already taken.
        if new_name != old_name and any(
            f["name"] == new_name for f in config["feeds"]
        ):
            messagebox.showerror(
                "Duplicate Name",
                f"A feed named \u201c{new_name}\u201d already exists.",
            )
            return
        for f in config["feeds"]:
            if f["name"] == old_name:
                f["name"] = new_name
                f["url"] = new_url
                if new_pattern:
                    f["match_pattern"] = new_pattern
                else:
                    f.pop("match_pattern", None)
                break
        if new_name != old_name:
            for m in config["monitors"]:
                m["feeds"] = [
                    new_name if fn == old_name else fn
                    for fn in m.get("feeds", [])
                ]
        self._save_config(config)
        if new_pattern != old_pattern and self._on_feed_pattern_change:
            self._on_feed_pattern_change(new_name)

    def _remove(self) -> None:
        feed_cfg = self._selected_feed_cfg()
        if not feed_cfg:
            return
        if not messagebox.askyesno(
            "Remove Feed", f"Remove \u2018{feed_cfg['name']}\u2019?"
        ):
            return
        config = self._get_config()
        old_name = feed_cfg["name"]
        old_url = feed_cfg.get("url", "")
        # Match by both name AND url so a duplicate-named feed doesn't also get removed.
        removed = False
        new_feeds = []
        for f in config["feeds"]:
            if (
                not removed
                and f["name"] == old_name
                and f.get("url", "") == old_url
            ):
                removed = True  # skip exactly one entry
            else:
                new_feeds.append(f)
        config["feeds"] = new_feeds
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

    # ── Inline pattern popup ───────────────────────────────────────────────

    def _build_preset_labels(self) -> list[str]:
        from watcher import PRESET_PATTERNS

        user = self._get_config().get("match_patterns", {})
        labels = [self._BUILTIN_SEP, self._NONE_LABEL] + list(
            PRESET_PATTERNS.keys()
        )
        if user:
            labels += [self._CUSTOM_SEP] + list(user.keys())
        return labels

    def _all_presets_map(self) -> dict[str, str]:
        from watcher import PRESET_PATTERNS

        user = self._get_config().get("match_patterns", {})
        return {**PRESET_PATTERNS, **user}

    def _close_pattern_popup(self) -> None:
        if self._pattern_popup is not None:
            try:
                self._pattern_popup.destroy()
            except tk.TclError:
                pass
            self._pattern_popup = None

    def _on_tree_motion(self, event) -> None:
        col = self._tree.identify_column(event.x)
        iid = self._tree.identify_row(event.y)
        if col == "#3" and iid:
            self._tree.config(cursor="hand2")
        else:
            self._tree.config(cursor="")

    def _on_tree_click(self, event) -> None:
        # If the click landed on the popup combobox itself (events bubble up
        # from the placed child widget to the tree), let the combobox handle it.
        if self._pattern_popup is not None:
            widget = self._tree.winfo_containing(event.x_root, event.y_root)
            if widget is self._pattern_popup:
                return

        col = self._tree.identify_column(event.x)
        if col != "#3":  # not the pattern column
            self._close_pattern_popup()
            return
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        # Re-clicking a different cell while popup is open → close it
        if self._pattern_popup is not None:
            self._close_pattern_popup()
            return
        self._show_pattern_popup(iid)

    def _show_pattern_popup(self, iid: str) -> None:
        bbox = self._tree.bbox(iid, "pattern")
        if not bbox:
            return
        x, y, w, h = bbox

        values = self._tree.item(iid)["values"]
        feed_name = values[0]
        feed_cfg = next(
            (f for f in self._get_config()["feeds"] if f["name"] == feed_name),
            None,
        )
        if feed_cfg is None:
            return

        current_pattern = feed_cfg.get("match_pattern", "")
        all_presets = self._all_presets_map()
        current_label = self._NONE_LABEL
        if current_pattern:
            for label, regex in all_presets.items():
                if regex == current_pattern:
                    current_label = label
                    break

        popup = ttk.Combobox(
            self._tree, values=self._build_preset_labels(), state="readonly"
        )
        popup.set(current_label)
        # Let the combobox use its natural height so text isn't clipped;
        # vertically center it within the cell row.
        popup.update_idletasks()
        natural_h = popup.winfo_reqheight()
        pop_y = y + (h - natural_h) // 2
        popup.place(x=x, y=pop_y, width=w)
        popup.focus_set()
        self._pattern_popup = popup

        def _commit(event=None) -> None:
            label = popup.get()
            if label in (self._BUILTIN_SEP, self._CUSTOM_SEP):
                return
            pattern = all_presets.get(label, "")  # "" → Full text (default)
            config = self._get_config()
            for f in config["feeds"]:
                if f["name"] == feed_name:
                    if pattern:
                        f["match_pattern"] = pattern
                    else:
                        f.pop("match_pattern", None)
                    break
            self._save_config(config)
            self._close_pattern_popup()
            self.refresh()
            if pattern != current_pattern and self._on_feed_pattern_change:
                self._on_feed_pattern_change(feed_name)

        popup.bind("<<ComboboxSelected>>", _commit)
        popup.bind("<Escape>", lambda _e: self._close_pattern_popup())

    def _preview(self) -> None:
        from gui.dialogs import FeedPreviewDialog

        feed_cfg = self._selected_feed_cfg()
        if not feed_cfg:
            messagebox.showinfo("Preview Feed", "Select a feed first.")
            return
        user_agent = self._get_config().get("user_agent", "RSSniper/1.0")
        conn = self._get_conn() if self._get_conn else None
        FeedPreviewDialog(self, feed_cfg, user_agent, conn=conn)
