import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import ttk
from typing import Callable, Optional

from gui.utils import attach_context_menu, fmt_dt


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

    _LABEL_NEW = "🆕 New"  # 🆕
    _LABEL_SEEN = "👁 Seen"  # 👁

    def __init__(
        self,
        parent: ttk.Notebook,
        on_check_now: Callable,
        on_minimize: Callable = None,
        get_config: Callable = None,
        on_mark_seen: Callable = None,
    ) -> None:
        super().__init__(parent)
        self._on_check_now = on_check_now
        self._on_minimize = on_minimize or (lambda: None)
        self._get_config = get_config or (lambda: {})
        self._on_mark_seen = on_mark_seen or (lambda item_id, seen: None)
        self._links: dict[str, str] = {}
        self._all_deals: list[dict] = []
        self._sort_col: Optional[str] = None
        self._sort_rev: bool = False
        self._build()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Top toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=(6, 0))

        self._status_var = tk.StringVar(value="No checks run yet.")
        ttk.Label(
            toolbar, textvariable=self._status_var, foreground="#555"
        ).pack(side="left")
        ttk.Button(toolbar, text="⬇ Tray", command=self._on_minimize).pack(
            side="right"
        )
        ttk.Button(
            toolbar, text="⚡ Check Now", command=self._on_check_now
        ).pack(side="right", padx=(0, 4))
        ttk.Button(toolbar, text="Clear", command=self._clear).pack(
            side="right", padx=(0, 4)
        )

        # Mark-seen / mark-new row
        mbar = ttk.Frame(self)
        mbar.pack(fill="x", padx=6, pady=(2, 0))
        ttk.Button(
            mbar, text="👁 Mark Seen", command=self._toolbar_mark_seen
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            mbar, text="🆕 Mark New", command=self._toolbar_mark_new
        ).pack(side="left")
        ttk.Label(
            mbar,
            text="  (Shift/Ctrl+click to select multiple)",
            foreground="#888",
            font=("TkDefaultFont", 8),
        ).pack(side="left", padx=(6, 0))

        # Filter bar
        fbar = ttk.Frame(self)
        fbar.pack(fill="x", padx=6, pady=(4, 0))

        ttk.Label(fbar, text="Filter:").pack(side="left")

        ttk.Label(fbar, text="  Status:").pack(side="left")
        self._filter_status = ttk.Combobox(
            fbar,
            values=["All", self._LABEL_NEW, self._LABEL_SEEN],
            state="readonly",
            width=12,
        )
        self._filter_status.set("All")
        self._filter_status.pack(side="left", padx=(2, 6))
        self._filter_status.bind(
            "<<ComboboxSelected>>", self._on_filter_change
        )

        ttk.Label(fbar, text="Monitor:").pack(side="left")
        self._filter_monitor = ttk.Combobox(
            fbar, values=["All"], state="readonly", width=14
        )
        self._filter_monitor.set("All")
        self._filter_monitor.pack(side="left", padx=(2, 6))
        self._filter_monitor.bind(
            "<<ComboboxSelected>>", self._on_filter_change
        )

        ttk.Label(fbar, text="Feed:").pack(side="left")
        self._filter_feed = ttk.Combobox(
            fbar, values=["All"], state="readonly", width=12
        )
        self._filter_feed.set("All")
        self._filter_feed.pack(side="left", padx=(2, 6))
        self._filter_feed.bind("<<ComboboxSelected>>", self._on_filter_change)

        ttk.Label(fbar, text="Max $:").pack(side="left")
        self._filter_price_var = tk.StringVar()
        price_entry = ttk.Entry(
            fbar, textvariable=self._filter_price_var, width=7
        )
        price_entry.pack(side="left", padx=(2, 6))
        price_entry.bind("<KeyRelease>", self._on_filter_change)

        ttk.Button(
            fbar, text="✕ Clear Filters", command=self._clear_filters
        ).pack(side="left", padx=(2, 0))

        # Treeview — extended for multi-select (Shift/Ctrl+click)
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=6, pady=6)

        self._tree = ttk.Treeview(
            frame,
            columns=self._COLUMNS,
            show="headings",
            selectmode="extended",
        )
        for col in self._COLUMNS:
            self._tree.heading(
                col,
                text=self._HEADINGS[col],
                command=lambda c=col: self._sort_by(c),
            )
            self._tree.column(
                col, width=self._WIDTHS[col], stretch=(col == "title")
            )

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.tag_configure("new", background="#1e5c33")
        self._tree.tag_configure("seen", background="#5c5218")

        # Double-click → preview + auto-mark seen
        self._tree.bind("<Double-1>", self._open_preview)
        self._tree.bind("<Control-a>", self._select_all)
        self._tree.bind("<Control-A>", self._select_all)

        attach_context_menu(
            self._tree,
            [
                ("🔍 Preview Deal", self._ctx_preview),
                ("🌐 Open in Browser", self._ctx_open),
                (None, None),
                ("👁 Mark as Seen", self._ctx_mark_seen),
                ("🆕 Mark as New", self._ctx_mark_new),
                (None, None),
                ("📋 Copy Title", self._ctx_copy_title),
                ("🔗 Copy URL", self._ctx_copy_url),
                (None, None),
                ("🗑 Dismiss", self._ctx_dismiss),
            ],
        )

        ttk.Label(
            self,
            text=(
                "Double-click to preview  ·  "
                "Shift/Ctrl+click selects multiple  ·  "
                "right-click for options"
            ),
            foreground="#888",
        ).pack(pady=(0, 4))

    # ── Data ───────────────────────────────────────────────────────────────

    def add_deal(
        self,
        monitor_name: str,
        feed_name: str,
        entry: dict,
        price: Optional[float],
        discovered_at=None,
        is_new: bool = True,
        item_id: str = "",
    ) -> None:
        discovered_str = fmt_dt(
            discovered_at if discovered_at is not None else datetime.now()
        )
        published_str = fmt_dt(entry.get("published", ""))
        price_str = f"${price:.2f}" if price is not None else "?"
        # Freshly found deals start as New; items loaded from DB start as Seen.
        status_label = self._LABEL_NEW if is_new else self._LABEL_SEEN
        tag = "new" if is_new else "seen"

        deal = {
            "item_id": item_id,
            "status_label": status_label,
            "tag": tag,
            "discovered": discovered_str,
            "published": published_str,
            "monitor": monitor_name,
            "feed": feed_name,
            "price_str": price_str,
            "price": price,
            "title": entry["title"],
            "url": entry.get("link", ""),
            "summary_html": entry.get("summary_html", ""),
        }
        self._all_deals.insert(0, deal)
        self._update_filter_options()
        self._apply_filters()

    def set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    # ── Seen / New helpers ─────────────────────────────────────────────────

    def _update_status_for_iids(
        self, iids: list[str], status_label: str, tag: str
    ) -> None:
        """Update status of the given tree iids in _all_deals, then re-render."""
        keys: set[tuple] = set()
        for iid in iids:
            url = self._links.get(iid)
            values = self._tree.item(iid)["values"]
            title = str(values[6]) if len(values) > 6 else ""
            keys.add((url, title))
        is_seen_bool = tag == "seen"
        for deal in self._all_deals:
            if (deal["url"], deal["title"]) in keys:
                deal["status_label"] = status_label
                deal["tag"] = tag
                if deal.get("item_id"):
                    self._on_mark_seen(deal["item_id"], is_seen_bool)
        self._apply_filters()

    def _mark_seen_iids(self, iids: list[str]) -> None:
        self._update_status_for_iids(iids, self._LABEL_SEEN, "seen")

    def _mark_new_iids(self, iids: list[str]) -> None:
        self._update_status_for_iids(iids, self._LABEL_NEW, "new")

    def _toolbar_mark_seen(self) -> None:
        sel = list(self._tree.selection())
        if sel:
            self._mark_seen_iids(sel)

    def _toolbar_mark_new(self) -> None:
        sel = list(self._tree.selection())
        if sel:
            self._mark_new_iids(sel)

    # ── Filters ────────────────────────────────────────────────────────────

    def _on_filter_change(self, _event=None) -> None:
        self._apply_filters()

    def _clear_filters(self) -> None:
        self._filter_status.set("All")
        self._filter_monitor.set("All")
        self._filter_feed.set("All")
        self._filter_price_var.set("")
        self._apply_filters()

    def _update_filter_options(self) -> None:
        monitors = ["All"] + sorted(
            {d["monitor"] for d in self._all_deals if d["monitor"]}
        )
        feeds = ["All"] + sorted(
            {d["feed"] for d in self._all_deals if d["feed"]}
        )
        cur_mon = self._filter_monitor.get()
        cur_feed = self._filter_feed.get()
        self._filter_monitor.config(values=monitors)
        self._filter_feed.config(values=feeds)
        if cur_mon not in monitors:
            self._filter_monitor.set("All")
        if cur_feed not in feeds:
            self._filter_feed.set("All")

    def _apply_filters(self) -> None:
        status_f = self._filter_status.get()
        monitor_f = self._filter_monitor.get()
        feed_f = self._filter_feed.get()
        price_raw = self._filter_price_var.get().strip().lstrip("$")
        try:
            max_price = float(price_raw) if price_raw else None
        except ValueError:
            max_price = None

        self._tree.delete(*self._tree.get_children())
        self._links.clear()

        for deal in self._all_deals:
            if status_f != "All" and deal["status_label"] != status_f:
                continue
            if monitor_f != "All" and deal["monitor"] != monitor_f:
                continue
            if feed_f != "All" and deal["feed"] != feed_f:
                continue
            if (
                max_price is not None
                and deal["price"] is not None
                and deal["price"] > max_price
            ):
                continue

            iid = self._tree.insert(
                "",
                "end",
                values=(
                    deal["status_label"],
                    deal["discovered"],
                    deal["published"],
                    deal["monitor"],
                    deal["feed"],
                    deal["price_str"],
                    deal["title"],
                ),
                tags=(deal["tag"],),
            )
            self._links[iid] = deal["url"]

    # ── Sort ───────────────────────────────────────────────────────────────

    def _sort_by(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False

        items = [
            (self._tree.set(iid, col), iid)
            for iid in self._tree.get_children("")
        ]
        items.sort(key=lambda x: x[0].lower(), reverse=self._sort_rev)
        for idx, (_, iid) in enumerate(items):
            self._tree.move(iid, "", idx)

        for c in self._COLUMNS:
            arrow = (" ▼" if self._sort_rev else " ▲") if c == col else ""
            self._tree.heading(
                c,
                text=self._HEADINGS[c] + arrow,
                command=lambda _c=c: self._sort_by(_c),
            )

    # ── Preview ────────────────────────────────────────────────────────────

    def _get_deal_for_iid(self, iid: str) -> Optional[dict]:
        url = self._links.get(iid)
        if not url:
            return None
        values = self._tree.item(iid)["values"]
        title = str(values[6]) if len(values) > 6 else ""
        for d in self._all_deals:
            if d["url"] == url and d["title"] == title:
                return d
        return None

    def _open_preview(self, _event=None) -> None:
        from gui.dialogs import DealPreviewDialog

        item = self._tree.focus()
        if not item:
            return
        deal = self._get_deal_for_iid(item)
        if deal is None:
            return
        # Auto-mark seen on preview
        self._mark_seen_iids([item])
        cfg = self._get_config()
        user_agent = cfg.get("user_agent", "RedditDealWatcher/1.0")
        DealPreviewDialog(self, deal, user_agent)

    # ── Context menu actions ───────────────────────────────────────────────

    def _ctx_preview(self) -> None:
        self._open_preview()

    def _ctx_open(self) -> None:
        item = self._tree.focus()
        if item and item in self._links:
            # Auto-mark seen on browser open
            self._mark_seen_iids([item])
            webbrowser.open(self._links[item])

    def _ctx_mark_seen(self) -> None:
        sel = list(self._tree.selection())
        if sel:
            self._mark_seen_iids(sel)

    def _ctx_mark_new(self) -> None:
        sel = list(self._tree.selection())
        if sel:
            self._mark_new_iids(sel)

    def _ctx_copy_title(self) -> None:
        item = self._tree.focus()
        if item:
            self.clipboard_clear()
            self.clipboard_append(str(self._tree.item(item)["values"][6]))

    def _ctx_copy_url(self) -> None:
        item = self._tree.focus()
        if item and item in self._links:
            self.clipboard_clear()
            self.clipboard_append(self._links[item])

    def _ctx_dismiss(self) -> None:
        sel = list(self._tree.selection())
        if not sel:
            return
        keys: set[tuple] = set()
        for iid in sel:
            url = self._links.get(iid)
            values = self._tree.item(iid)["values"]
            title = str(values[6]) if len(values) > 6 else ""
            keys.add((url, title))
        self._all_deals = [
            d for d in self._all_deals if (d["url"], d["title"]) not in keys
        ]
        for iid in sel:
            self._links.pop(iid, None)
            self._tree.delete(iid)
        self._update_filter_options()

    # ── Theme ──────────────────────────────────────────────────────────────

    def set_theme(self, is_dark: bool) -> None:
        if is_dark:
            self._tree.tag_configure("new", background="#1e5c33")
            self._tree.tag_configure("seen", background="#5c5218")
        else:
            self._tree.tag_configure("new", background="#c8f0c8")
            self._tree.tag_configure("seen", background="#f5ec8a")

    # ── Clear ──────────────────────────────────────────────────────────────

    def clear(self) -> None:
        self._tree.delete(*self._tree.get_children())
        self._links.clear()
        self._all_deals.clear()
        self._update_filter_options()

    def _select_all(self, _event=None) -> str:
        self._tree.selection_set(self._tree.get_children())
        return "break"

    def _clear(self) -> None:
        self.clear()
