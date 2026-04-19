import logging
import queue
import tkinter as tk
from tkinter import scrolledtext, ttk


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
    _LEVEL_COLORS = {
        "DEBUG": "#888888",
        "INFO": "#1a1a1a",
        "WARNING": "#b36b00",
        "ERROR": "#cc0000",
        "CRITICAL": "#cc0000",
    }

    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=(6, 0))
        ttk.Button(toolbar, text="Clear", command=self._clear).pack(
            side="right"
        )

        self._text = scrolledtext.ScrolledText(
            self,
            state="disabled",
            wrap="word",
            font=("Consolas", 9),
            relief="flat",
        )
        self._text.pack(fill="both", expand=True, padx=6, pady=6)

        for level, color in self._LEVEL_COLORS.items():
            self._text.tag_configure(level, foreground=color)

    def append(self, level: str, message: str) -> None:
        tag = level if level in self._LEVEL_COLORS else "INFO"
        self._text.config(state="normal")
        self._text.insert("end", message + "\n", tag)
        self._text.see("end")
        self._text.config(state="disabled")

    def _clear(self) -> None:
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._text.config(state="disabled")
