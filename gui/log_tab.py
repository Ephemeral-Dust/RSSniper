import logging
import queue
import tkinter as tk
from tkinter import scrolledtext, ttk
from typing import Callable

from gui.utils import LOG_COLORS_DARK

# Ordered from most-verbose to least-verbose
_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]
_LEVEL_NUM = {name: getattr(logging, name) for name in _LEVELS}


class QueueHandler(logging.Handler):
    """Routes log records into a queue so the GUI can consume them safely."""

    def __init__(self, log_queue: queue.Queue) -> None:
        super().__init__()
        self.log_queue = log_queue
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S"
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.log_queue.put(
                {"type": "log", "level": record.levelname, "message": msg}
            )
        except Exception:
            self.handleError(record)


class LogTab(ttk.Frame):
    _LEVEL_COLORS = LOG_COLORS_DARK

    def __init__(
        self,
        parent: ttk.Notebook,
        on_check_now: Callable = None,
        on_minimize: Callable = None,
        level_filter: str = "DEBUG",
        save_to_file: bool = False,
        on_level_change: Callable[[str], None] = None,
        on_save_to_file_change: Callable[[bool], None] = None,
    ) -> None:
        super().__init__(parent)
        self._on_check_now = on_check_now or (lambda: None)
        self._on_minimize = on_minimize or (lambda: None)
        self._on_level_change = on_level_change or (lambda _: None)
        self._on_save_to_file_change = on_save_to_file_change or (
            lambda _: None
        )

        # Clamp to a valid level
        self._level_filter = (
            level_filter if level_filter in _LEVELS else "DEBUG"
        )
        self._save_to_file = save_to_file

        # Full message buffer: list of (levelname, formatted_message)
        self._all_messages: list[tuple[str, str]] = []

        self._build()

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=(6, 0))

        # Right side first (so they don't get squeezed)
        ttk.Button(toolbar, text="⬇ Tray", command=self._on_minimize).pack(
            side="right"
        )
        ttk.Button(
            toolbar, text="⚡ Check Now", command=self._on_check_now
        ).pack(side="right", padx=(0, 4))
        ttk.Button(toolbar, text="Clear", command=self._clear).pack(
            side="right", padx=(0, 4)
        )

        # Left side: level filter + file-log toggle
        ttk.Label(toolbar, text="Level:").pack(side="left")
        self._level_var = tk.StringVar(value=self._level_filter)
        level_cb = ttk.Combobox(
            toolbar,
            textvariable=self._level_var,
            values=_LEVELS,
            state="readonly",
            width=9,
        )
        level_cb.pack(side="left", padx=(4, 12))
        level_cb.bind("<<ComboboxSelected>>", self._on_level_selected)

        self._file_var = tk.BooleanVar(value=self._save_to_file)
        ttk.Checkbutton(
            toolbar,
            text="Save log to file",
            variable=self._file_var,
            command=self._on_file_toggled,
        ).pack(side="left")

        self._text = scrolledtext.ScrolledText(
            self,
            state="disabled",
            wrap="word",
            font=("Consolas", 9),
            relief="flat",
            background="#1c1c1c",
            foreground="#d4d4d4",
            insertbackground="#d4d4d4",
            selectbackground="#0078d4",
            selectforeground="#ffffff",
        )
        self._text.pack(fill="both", expand=True, padx=6, pady=6)

        for level, color in self._LEVEL_COLORS.items():
            self._text.tag_configure(level, foreground=color)

    # ── Public API ─────────────────────────────────────────────────────────────

    def append(self, level: str, message: str) -> None:
        """Buffer the message and display it if it passes the current filter."""
        self._all_messages.append((level, message))
        if _LEVEL_NUM.get(level, 0) >= _LEVEL_NUM[self._level_filter]:
            self._write_line(level, message)

    def set_theme(self, is_dark: bool) -> None:
        """Called by app.py when the theme changes."""
        from gui.utils import LOG_COLORS_DARK, LOG_COLORS_LIGHT

        colors = LOG_COLORS_DARK if is_dark else LOG_COLORS_LIGHT
        bg = "#1c1c1c" if is_dark else "#ffffff"
        fg = "#d4d4d4" if is_dark else "#1a1a1a"
        self._text.config(background=bg, foreground=fg)
        for lvl, color in colors.items():
            self._text.tag_configure(lvl, foreground=color)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _write_line(self, level: str, message: str) -> None:
        tag = level if level in self._LEVEL_COLORS else "INFO"
        self._text.config(state="normal")
        self._text.insert("end", message + "\n", tag)
        self._text.see("end")
        self._text.config(state="disabled")

    def _redraw(self) -> None:
        """Rebuild the visible text from the buffer using the current filter."""
        min_num = _LEVEL_NUM[self._level_filter]
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        for level, message in self._all_messages:
            if _LEVEL_NUM.get(level, 0) >= min_num:
                tag = level if level in self._LEVEL_COLORS else "INFO"
                self._text.insert("end", message + "\n", tag)
        self._text.see("end")
        self._text.config(state="disabled")

    def _on_level_selected(self, _event=None) -> None:
        new_level = self._level_var.get()
        if new_level == self._level_filter:
            return
        self._level_filter = new_level
        self._redraw()
        self._on_level_change(new_level)

    def _on_file_toggled(self) -> None:
        self._save_to_file = self._file_var.get()
        self._on_save_to_file_change(self._save_to_file)

    def _clear(self) -> None:
        self._all_messages.clear()
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._text.config(state="disabled")
