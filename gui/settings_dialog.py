import tkinter as tk
from tkinter import ttk
from typing import Optional


def _center_on_parent(dialog: tk.Toplevel, parent: tk.Widget) -> None:
    dialog.update_idletasks()
    pw = (
        parent.winfo_rootx()
        + parent.winfo_width() // 2
        - dialog.winfo_width() // 2
    )
    ph = (
        parent.winfo_rooty()
        + parent.winfo_height() // 2
        - dialog.winfo_height() // 2
    )
    dialog.geometry(f"+{pw}+{ph}")


class SettingsDialog(tk.Toplevel):
    """Application-wide settings dialog.

    On OK, ``self.result`` contains a shallow-merged update dict that the
    caller should apply on top of the existing config and then save.
    """

    def __init__(self, parent: tk.Widget, config: dict) -> None:
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self.grab_set()
        self._cfg = config
        self.result: Optional[dict] = None
        self._build()
        _center_on_parent(self, parent)
        self.bind("<Escape>", lambda _: self.destroy())

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        # ── Watcher ────────────────────────────────────────────────────────────
        wf = ttk.LabelFrame(outer, text=" Watcher ", padding=10)
        wf.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(wf, text="Poll interval (minutes):").grid(
            row=0, column=0, sticky="w", pady=3
        )
        self._interval = ttk.Spinbox(wf, from_=1, to=1440, width=8)
        self._interval.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=3)
        self._interval.set(self._cfg.get("check_interval_minutes", 15))

        self._startup_var = tk.BooleanVar(
            value=self._cfg.get("check_on_startup", True)
        )
        ttk.Checkbutton(
            wf,
            text="Check feeds automatically on startup",
            variable=self._startup_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=3)

        # ── History ────────────────────────────────────────────────────────────
        hf = ttk.LabelFrame(outer, text=" History ", padding=10)
        hf.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(hf, text="Lookback window (days):").grid(
            row=0, column=0, sticky="w", pady=3
        )
        self._lookback = ttk.Spinbox(hf, from_=1, to=30, width=8)
        self._lookback.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=3)
        self._lookback.set(self._cfg.get("max_lookback_days", 3))
        ttk.Label(
            hf,
            text="How far back to fetch posts when first monitoring a feed,\n"
            "and how far back to scan the local database for missed deals.",
            foreground="#888",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=(0, 0))

        ttk.Label(hf, text="Max entries per feed (per check):").grid(
            row=2, column=0, sticky="w", pady=(10, 3)
        )
        self._max_entries = ttk.Spinbox(
            hf, from_=100, to=5000, increment=100, width=8
        )
        self._max_entries.grid(
            row=2, column=1, sticky="w", padx=(8, 0), pady=(10, 3)
        )
        self._max_entries.set(self._cfg.get("max_entries_per_feed", 1000))

        # ── Network ────────────────────────────────────────────────────────────
        nf = ttk.LabelFrame(outer, text=" Network ", padding=10)
        nf.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(nf, text="Request timeout (seconds):").grid(
            row=0, column=0, sticky="w", pady=3
        )
        self._timeout = ttk.Spinbox(nf, from_=5, to=120, width=8)
        self._timeout.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=3)
        self._timeout.set(self._cfg.get("request_timeout_seconds", 15))

        ttk.Label(nf, text="Delay between paginated requests (seconds):").grid(
            row=1, column=0, sticky="w", pady=3
        )
        self._page_delay = ttk.Spinbox(
            nf, from_=0.0, to=10.0, increment=0.25, width=8
        )
        self._page_delay.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=3)
        self._page_delay.set(self._cfg.get("page_delay_seconds", 0.75))

        ttk.Label(nf, text="User-Agent string:").grid(
            row=2, column=0, sticky="w", pady=(10, 3)
        )
        self._user_agent = ttk.Entry(nf, width=44)
        self._user_agent.grid(
            row=2, column=1, sticky="ew", padx=(8, 0), pady=(10, 3)
        )
        self._user_agent.insert(
            0,
            self._cfg.get(
                "user_agent", "RedditDealWatcher/1.0 (personal use)"
            ),
        )
        nf.columnconfigure(1, weight=1)

        # ── Notifications ──────────────────────────────────────────────────────
        ntf = ttk.LabelFrame(outer, text=" Notifications ", padding=10)
        ntf.grid(row=3, column=0, sticky="ew", pady=(0, 8))

        notify_cfg: dict = self._cfg.get("notifications", {})

        self._notify_desktop_var = tk.BooleanVar(
            value=notify_cfg.get("desktop", True)
        )
        ttk.Checkbutton(
            ntf,
            text="Show desktop notification for new deal matches",
            variable=self._notify_desktop_var,
        ).grid(row=0, column=0, sticky="w", pady=3)

        self._notify_historical_var = tk.BooleanVar(
            value=notify_cfg.get("notify_historical", False)
        )
        ttk.Checkbutton(
            ntf,
            text="Show desktop notification for historical database matches",
            variable=self._notify_historical_var,
        ).grid(row=1, column=0, sticky="w", pady=3)

        self._notify_console_var = tk.BooleanVar(
            value=notify_cfg.get("console", True)
        )
        ttk.Checkbutton(
            ntf,
            text="Log matches to the Log tab",
            variable=self._notify_console_var,
        ).grid(row=2, column=0, sticky="w", pady=3)

        # ── Buttons ────────────────────────────────────────────────────────────
        sep = ttk.Separator(outer, orient="horizontal")
        sep.grid(row=4, column=0, sticky="ew", pady=(4, 0))

        btn_frame = ttk.Frame(outer)
        btn_frame.grid(row=5, column=0, sticky="e", pady=(10, 0))
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(
            side="right"
        )
        ttk.Button(btn_frame, text="Save", command=self._submit).pack(
            side="right", padx=(0, 6)
        )

        outer.columnconfigure(0, weight=1)

    # ── Submit ─────────────────────────────────────────────────────────────────

    def _submit(self) -> None:
        try:
            interval = int(float(self._interval.get()))
            if interval < 1:
                raise ValueError
        except ValueError:
            self._interval.config(foreground="red")
            return

        try:
            lookback = int(float(self._lookback.get()))
            if lookback < 1:
                raise ValueError
        except ValueError:
            self._lookback.config(foreground="red")
            return

        try:
            max_entries = int(float(self._max_entries.get()))
            if max_entries < 100:
                raise ValueError
        except ValueError:
            self._max_entries.config(foreground="red")
            return

        try:
            timeout = int(float(self._timeout.get()))
            if timeout < 1:
                raise ValueError
        except ValueError:
            self._timeout.config(foreground="red")
            return

        try:
            page_delay = float(self._page_delay.get())
            if page_delay < 0:
                raise ValueError
        except ValueError:
            self._page_delay.config(foreground="red")
            return

        user_agent = self._user_agent.get().strip()
        if not user_agent:
            self._user_agent.config(foreground="red")
            return

        self.result = {
            "check_interval_minutes": interval,
            "check_on_startup": self._startup_var.get(),
            "max_lookback_days": lookback,
            "max_entries_per_feed": max_entries,
            "request_timeout_seconds": timeout,
            "page_delay_seconds": page_delay,
            "user_agent": user_agent,
            "notifications": {
                "desktop": self._notify_desktop_var.get(),
                "notify_historical": self._notify_historical_var.get(),
                "console": self._notify_console_var.get(),
            },
        }
        self.destroy()
