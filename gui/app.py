import logging
import queue
import threading
import time
from datetime import datetime
from typing import Optional

import schedule
import tkinter as tk
from tkinter import messagebox, ttk

from config import load_config, save_config
from database import DB_FILE, init_db, get_recent_deal_matches
from notifications import notify_desktop
from watcher import run_check, MAX_LOOKBACK_DAYS
from gui.deals_tab import DealsTab
from gui.feeds_tab import FeedsTab
from gui.monitors_tab import MonitorsTab
from gui.log_tab import LogTab, QueueHandler


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("RedditDealWatcher")
        self.geometry("1150x720")
        self.minsize(900, 560)

        self._config = load_config()
        self._conn = init_db(DB_FILE)
        self._queue: queue.Queue = queue.Queue()

        self._checking = False
        self._watcher_running = False
        self._watcher_thread: Optional[threading.Thread] = None

        self._setup_style()
        self._build_menu()
        self._build_ui()
        self._setup_logging()
        self._start_scheduler()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_queue)
        self.after(
            200, self._load_historical_deals
        )  # populate from DB immediately
        if self._config.get("check_on_startup", True):
            self.after(1500, self._trigger_check)  # auto-check on startup

    # ── Style ──────────────────────────────────────────────────────────────────

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        for theme in ("vista", "clam"):
            try:
                style.theme_use(theme)
                break
            except tk.TclError:
                continue
        style.configure("Status.TLabel", foreground="#555555", padding=(6, 2))

    # ── Menu ───────────────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(
            label="Reload Config", command=self._reload_config
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        watcher_menu = tk.Menu(menubar, tearoff=False)
        watcher_menu.add_command(
            label="Check Now", command=self._trigger_check
        )
        watcher_menu.add_separator()
        watcher_menu.add_command(
            label="Settings…", command=self._open_settings
        )
        menubar.add_cascade(label="Watcher", menu=watcher_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=4)

        ttk.Button(
            toolbar, text="⚡ Check Now", command=self._trigger_check
        ).pack(side="left")
        self._interval_var = tk.StringVar(
            value=f"  Polling every {self._config.get('check_interval_minutes', 15)} min"
        )
        ttk.Label(
            toolbar, textvariable=self._interval_var, foreground="#555"
        ).pack(side="left", padx=8)

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self._deals_tab = DealsTab(notebook, on_check_now=self._trigger_check)
        self._feeds_tab = FeedsTab(
            notebook,
            get_config=lambda: self._config,
            save_config=self._on_config_save,
            get_conn=lambda: self._conn,
        )
        self._monitors_tab = MonitorsTab(
            notebook,
            get_config=lambda: self._config,
            save_config=self._on_config_save,
        )
        self._log_tab = LogTab(notebook)

        notebook.add(self._deals_tab, text="  Deals  ")
        notebook.add(self._feeds_tab, text="  Feeds  ")
        notebook.add(self._monitors_tab, text="  Monitors  ")
        notebook.add(self._log_tab, text="  Log  ")

        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(
            self,
            textvariable=self._status_var,
            style="Status.TLabel",
            relief="sunken",
            anchor="w",
        ).pack(fill="x", side="bottom")

    # ── Logging ────────────────────────────────────────────────────────────────

    def _setup_logging(self) -> None:
        handler = QueueHandler(self._queue)
        watcher_log = logging.getLogger("watcher")
        watcher_log.setLevel(logging.DEBUG)
        watcher_log.addHandler(handler)

    # ── Scheduler ─────────────────────────────────────────────────────────────

    def _start_scheduler(self) -> None:
        interval = self._config.get("check_interval_minutes", 15)
        schedule.clear()
        schedule.every(interval).minutes.do(self._trigger_check)
        self._watcher_running = True
        self._watcher_thread = threading.Thread(
            target=self._scheduler_loop, daemon=True, name="watcher-scheduler"
        )
        self._watcher_thread.start()

    def _scheduler_loop(self) -> None:
        while self._watcher_running:
            schedule.run_pending()
            time.sleep(5)

    # ── Check logic ────────────────────────────────────────────────────────────

    def _load_historical_deals(
        self, check_started_at: str | None = None
    ) -> None:
        """Populate the Deals tab from deal_matches already in the database.

        Rows whose matched_at >= check_started_at are marked as New;
        all others are marked Historical.
        """
        from datetime import timedelta, timezone
        from datetime import datetime as _dt
        from gui.utils import fmt_dt

        lookback = self._config.get("max_lookback_days", MAX_LOOKBACK_DAYS)
        since = _dt.now(timezone.utc) - timedelta(days=lookback)
        matches = get_recent_deal_matches(self._conn, since)
        for row in matches:
            price = row["price"]
            entry = {
                "title": row["title"],
                "link": row["url"],
                "published": row["published"],
            }
            is_new = (
                check_started_at is not None
                and row["matched_at"] >= check_started_at
            )
            self._deals_tab.add_deal(
                row["monitor_name"],
                row["feed"],
                entry,
                price,
                discovered_at=row["matched_at"],
                is_new=is_new,
            )
        if matches:
            self._set_status(
                f"Loaded {len(matches)} historical deal(s) from database."
            )

    # ── Check logic ────────────────────────────────────────────────────────────

    def _trigger_check(self) -> None:
        if self._checking:
            return
        self._checking = True
        self._set_status("Checking feeds…")
        threading.Thread(
            target=self._do_check, daemon=True, name="watcher-check"
        ).start()

    def _do_check(self) -> None:
        check_started_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        try:
            run_check(self._config, self._conn, on_match=self._on_match)
        finally:
            self._queue.put(
                {"type": "check_end", "check_started_at": check_started_at}
            )

    def _on_match(
        self, *, monitor, feed_name, entry, price, notify=True
    ) -> None:
        self._queue.put(
            {
                "type": "deal",
                "monitor_name": monitor["name"],
                "feed_name": feed_name,
                "entry": entry,
                "price": price,
                "is_new": True,
            }
        )
        notify_cfg = self._config.get("notifications", {})
        if notify and notify_cfg.get("desktop", True):
            price_label = f" — ${price:.2f}" if price is not None else ""
            notify_desktop(
                f"Deal: {monitor['name']}{price_label}",
                entry["title"],
            )

    # ── Queue polling ──────────────────────────────────────────────────────────

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                mtype = msg.get("type")
                if mtype == "deal":
                    self._deals_tab.add_deal(
                        msg["monitor_name"],
                        msg["feed_name"],
                        msg["entry"],
                        msg["price"],
                        is_new=msg.get("is_new", True),
                    )
                    title_short = msg["entry"]["title"][:60]
                    self._set_status(
                        f"New deal — {msg['monitor_name']}: {title_short}"
                    )
                elif mtype == "log":
                    self._log_tab.append(msg["level"], msg["message"])
                elif mtype == "check_end":
                    self._checking = False
                    ts = datetime.now().strftime("%H:%M:%S")
                    self._set_status(f"Last checked: {ts}")
                    self._deals_tab.set_status(f"Last check: {ts}")
                    # Reload deals from DB so UI always reflects deal_matches
                    self._deals_tab.clear()
                    self._load_historical_deals(
                        check_started_at=msg.get("check_started_at")
                    )
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    # ── Config callbacks ───────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        from gui.settings_dialog import SettingsDialog

        dlg = SettingsDialog(self, self._config)
        self.wait_window(dlg)
        if not dlg.result:
            return
        # Merge result into existing config (preserves feeds/monitors/etc.)
        updated = dict(self._config)
        updated.update(dlg.result)
        self._on_config_save(updated)
        self._start_scheduler()  # restart scheduler with new interval

    def _on_config_save(self, config: dict) -> None:
        self._config = config
        save_config(config)
        self._feeds_tab.refresh()
        self._monitors_tab.refresh()
        interval = config.get("check_interval_minutes", 15)
        self._interval_var.set(f"  Polling every {interval} min")

    def _reload_config(self) -> None:
        self._config = load_config()
        self._feeds_tab.refresh()
        self._monitors_tab.refresh()
        self._set_status("Config reloaded.")

    # ── Misc ───────────────────────────────────────────────────────────────────

    def _set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About",
            "RedditDealWatcher\n\n"
            "Monitor RSS feeds for deals matching keywords and price thresholds.\n\n"
            "Feeds tab  →  add/remove/preview RSS feeds\n"
            "Monitors tab  →  configure keyword & price rules\n"
            "Deals tab  →  matched deals (double-click to open)\n"
            "Log tab  →  live watcher activity",
        )

    def _on_close(self) -> None:
        self._watcher_running = False
        try:
            self._conn.close()
        except Exception:
            pass
        self.destroy()


def launch_gui() -> None:
    app = App()
    app.mainloop()
