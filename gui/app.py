import ctypes
import logging
import queue
import sys
import threading
import time
from datetime import datetime
from typing import Optional

import schedule
import sv_ttk
import tkinter as tk
from tkinter import messagebox, ttk

try:
    import pystray
    from PIL import Image, ImageDraw

    _TRAY_AVAILABLE = True
except ImportError:
    _TRAY_AVAILABLE = False

from config import load_config, save_config
from database import DB_FILE, init_db, get_recent_deal_matches
from notifications import notify_desktop
from paths import get_asset_dir
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
        self._tray_icon: Optional[object] = None
        self._tray_started = False

        self._setup_style()  # sets _menu_kw and sv_ttk theme
        self._menubar_frame = tk.Frame(self)  # persistent frame, always at top
        self._menubar_frame.pack(fill="x", side="top")
        self._build_menu()
        self._build_ui()
        self._setup_logging()
        self._start_scheduler()
        self._apply_icon()
        self._build_tray_icon()
        # Re-apply theme now that all tabs exist so they get correct colours
        self._apply_theme(self._config.get("theme", "dark"))

        # X button minimizes to tray when available, otherwise closes.
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_queue)
        self.after(
            200, self._load_historical_deals
        )  # populate from DB immediately
        if self._config.get("check_on_startup", True):
            self.after(1500, self._trigger_check)  # auto-check on startup

    # ── Style ──────────────────────────────────────────────────────────────────

    _LOG_COLORS_DARK = {
        "DEBUG": "#888888",
        "INFO": "#d4d4d4",
        "WARNING": "#f0a030",
        "ERROR": "#f04040",
        "CRITICAL": "#ff4040",
    }
    _LOG_COLORS_LIGHT = {
        "DEBUG": "#888888",
        "INFO": "#1a1a1a",
        "WARNING": "#b36b00",
        "ERROR": "#cc0000",
        "CRITICAL": "#cc0000",
    }

    def _setup_style(self) -> None:
        # Initial menu_kw placeholder (populated by _apply_theme)
        self._menu_kw: dict = {}
        style = ttk.Style(self)
        style.configure("Status.TLabel", padding=(6, 2))
        self._apply_theme(self._config.get("theme", "dark"))

    def _apply_theme(self, theme: str) -> None:
        """Apply dark/light/system theme. Safe to call after initial setup."""
        if theme == "system":
            # Detect system preference via Windows registry if available
            resolved = "dark"
            if sys.platform == "win32":
                try:
                    import winreg

                    key = winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    )
                    val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                    resolved = "light" if val == 1 else "dark"
                except Exception:
                    resolved = "dark"
        else:
            resolved = theme  # "dark" or "light"

        sv_ttk.set_theme(resolved)

        is_dark = resolved == "dark"
        menu_bg = "#1c1c1c" if is_dark else "#f0f0f0"
        menu_fg = "#ffffff" if is_dark else "#000000"
        menu_abg = "#0078d4"
        menu_afg = "#ffffff"
        self._menu_kw = dict(
            background=menu_bg,
            foreground=menu_fg,
            activebackground=menu_abg,
            activeforeground=menu_afg,
            relief="flat",
            borderwidth=0,
        )

        # Update title bar
        self._apply_dark_titlebar(is_dark)

        # Rebuild the custom menu bar with new colours
        if hasattr(self, "_menubar_frame"):
            self._build_menu()

        # Update deals tab row tag colours
        if hasattr(self, "_deals_tab"):
            self._deals_tab.set_theme(is_dark)

        # Update log tab colours if already built
        if hasattr(self, "_log_tab"):
            colors = (
                self._LOG_COLORS_DARK if is_dark else self._LOG_COLORS_LIGHT
            )
            text_widget = self._log_tab._text
            bg = "#1c1c1c" if is_dark else "#ffffff"
            fg = "#d4d4d4" if is_dark else "#1a1a1a"
            text_widget.config(background=bg, foreground=fg)
            for level, color in colors.items():
                text_widget.tag_configure(level, foreground=color)

    def _apply_dark_titlebar(self, is_dark: bool = True) -> None:
        """Ask Windows DWM to render a dark or light title bar on Windows 10/11."""
        if sys.platform != "win32":
            return
        try:
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            self.update()  # ensure HWND is realised
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(ctypes.c_int(1 if is_dark else 0)),
                ctypes.sizeof(ctypes.c_int),
            )
        except Exception:
            pass  # silently ignore on unsupported Windows versions

    # ── Menu ───────────────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        # Clear and repopulate the persistent _menubar_frame so pack order
        # is never disturbed when the theme changes.
        for w in self._menubar_frame.winfo_children():
            w.destroy()

        is_dark = self._menu_kw.get("foreground", "#ffffff") == "#ffffff"
        bg = self._menu_kw.get("background", "#1c1c1c")
        fg = self._menu_kw.get("foreground", "#ffffff")
        hover_bg = "#2d2d2d" if is_dark else "#dcdcdc"

        self._menubar_frame.config(bg=bg)

        def _mb(label: str) -> tk.Menubutton:
            btn = tk.Menubutton(
                self._menubar_frame,
                text=label,
                bg=bg,
                fg=fg,
                activebackground=hover_bg,
                activeforeground=fg,
                relief="flat",
                padx=8,
                pady=4,
                bd=0,
                cursor="arrow",
            )
            btn.pack(side="left")
            return btn

        # File menu — menu must be a child of its Menubutton
        mb_file = _mb("File")
        file_menu = tk.Menu(mb_file, tearoff=False, **self._menu_kw)
        file_menu.add_command(
            label="Reload Config", command=self._reload_config
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        mb_file.config(menu=file_menu)

        mb_settings = _mb("Settings")
        settings_menu = tk.Menu(mb_settings, tearoff=False, **self._menu_kw)
        settings_menu.add_command(
            label="Settings…", command=self._open_settings
        )
        mb_settings.config(menu=settings_menu)

        mb_help = _mb("Help")
        help_menu = tk.Menu(mb_help, tearoff=False, **self._menu_kw)
        help_menu.add_command(label="About", command=self._show_about)
        mb_help.config(menu=help_menu)

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

        ttk.Button(
            toolbar, text="⬇ Tray", command=self._minimize_to_tray
        ).pack(side="right")

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

    # ── System tray ────────────────────────────────────────────────────────────

    def _apply_icon(self) -> None:
        """Set the window titlebar/taskbar icon."""
        ico = get_asset_dir() / "icons" / "icon.ico"
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

    def _build_tray_icon(self) -> None:
        if not _TRAY_AVAILABLE:
            return
        # Use the real .ico if available, otherwise fall back to a drawn icon.
        ico_path = get_asset_dir() / "icons" / "icon.ico"
        if ico_path.exists():
            img = Image.open(str(ico_path)).convert("RGBA").resize((64, 64))
        else:
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([2, 2, 62, 62], fill="#e94560")
            draw.ellipse([22, 18, 42, 46], outline="white", width=5)
            draw.line([42, 32, 54, 52], fill="white", width=5)

        def _on_tray_show(icon, item):
            self.after(0, self._restore_from_tray)

        def _on_tray_check(icon, item):
            self.after(0, self._trigger_check)

        def _on_tray_exit(icon, item):
            self.after(0, self._exit_app)

        menu = pystray.Menu(
            pystray.MenuItem("Show", _on_tray_show, default=True),
            pystray.MenuItem("Check Now", _on_tray_check),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", _on_tray_exit),
        )
        self._tray_icon = pystray.Icon(
            "RedditDealWatcher", img, "RedditDealWatcher", menu
        )

    def _minimize_to_tray(self) -> None:
        if self._tray_icon is None:
            # pystray not available — just iconify normally.
            self.iconify()
            return
        self.withdraw()
        if not self._tray_started:
            self._tray_icon.run_detached()
            self._tray_started = True
        else:
            self._tray_icon.visible = True

    def _restore_from_tray(self) -> None:
        if self._tray_icon is not None:
            self._tray_icon.visible = False
        self.deiconify()
        self.lift()
        self.focus_force()

    def _exit_app(self) -> None:
        if self._tray_icon is not None and self._tray_started:
            self._tray_icon.stop()
        self._on_close()

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
        self._apply_theme(updated.get("theme", "dark"))
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
        if self._tray_icon is not None and self._tray_started:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        try:
            self._conn.close()
        except Exception:
            pass
        self.destroy()


def launch_gui() -> None:
    app = App()
    app.mainloop()
