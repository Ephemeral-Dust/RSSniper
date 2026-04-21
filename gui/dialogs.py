import re
import tkinter as tk
import webbrowser
from html.parser import HTMLParser
from tkinter import messagebox, ttk
from typing import Callable, Optional

from gui.utils import apply_dialog_icon, fmt_dt


def _center_on_parent(dialog: tk.Toplevel, parent: tk.Widget) -> None:
    dialog.update_idletasks()
    # For windows with an explicit geometry("WxH") call, winfo_reqwidth/height
    # may return 1 because PanedWindow/Treeview have tiny natural sizes.
    # Parse the stored geometry string as a reliable source of the real size.
    geo = dialog.geometry()  # "WxH+X+Y"
    wh = geo.split("+")[0].split("x")
    geo_w, geo_h = int(wh[0]), int(wh[1])
    dw = max(geo_w, dialog.winfo_reqwidth())
    dh = max(geo_h, dialog.winfo_reqheight())
    pw = parent.winfo_rootx() + parent.winfo_width() // 2 - dw // 2
    ph = parent.winfo_rooty() + parent.winfo_height() // 2 - dh // 2
    dialog.geometry(f"{dw}x{dh}+{pw}+{ph}")
    dialog.deiconify()


class AddFeedDialog(tk.Toplevel):
    _NONE_LABEL = "Full text (default)"
    _BUILTIN_SEP = "\u2500\u2500 Built-in presets \u2500\u2500"
    _CUSTOM_SEP = "\u2500\u2500 My presets \u2500\u2500"

    def __init__(
        self,
        parent: tk.Widget,
        initial: dict | None = None,
        get_config: Callable = None,
        save_config: Callable = None,
    ) -> None:
        super().__init__(parent)
        self.withdraw()
        self._initial = initial
        self._get_config = get_config or (lambda: {})
        self._save_config = save_config or (lambda _c: None)
        self.title("Edit Feed" if initial else "Add Feed")
        self.resizable(False, False)
        self.grab_set()
        apply_dialog_icon(self)
        self.result: dict | None = None
        self._build()
        _center_on_parent(self, parent)

    def _all_presets(self) -> dict[str, str]:
        """Built-in presets merged with user-saved presets (user wins on name clash)."""
        from watcher import PRESET_PATTERNS

        user = self._get_config().get("match_patterns", {})
        return {**PRESET_PATTERNS, **user}

    def _refresh_preset_values(self) -> None:
        from watcher import PRESET_PATTERNS

        user = self._get_config().get("match_patterns", {})
        labels = [self._BUILTIN_SEP, self._NONE_LABEL] + list(
            PRESET_PATTERNS.keys()
        )
        if user:
            labels += [self._CUSTOM_SEP] + list(user.keys())
        self._preset.config(values=labels)

    def _build(self) -> None:
        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Name:").grid(row=0, column=0, sticky="w", pady=4)
        self._name = ttk.Entry(f, width=38)
        self._name.grid(row=0, column=1, sticky="ew", pady=4, padx=(8, 0))
        ttk.Label(f, text='e.g. "r/mechmarket"', foreground="#888").grid(
            row=0, column=2, sticky="w", padx=(6, 0)
        )

        ttk.Label(f, text="URL:").grid(row=1, column=0, sticky="w", pady=4)
        self._url = ttk.Entry(f, width=38)
        self._url.grid(
            row=1, column=1, columnspan=2, sticky="ew", pady=4, padx=(8, 0)
        )

        ttk.Label(f, text="Type:").grid(row=2, column=0, sticky="w", pady=4)
        self._type = ttk.Combobox(
            f, values=["reddit", "rss"], state="readonly", width=10
        )
        self._type.set("reddit")
        self._type.grid(row=2, column=1, sticky="w", pady=4, padx=(8, 0))

        sep = ttk.Separator(f, orient="horizontal")
        sep.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        # ── Match pattern ──────────────────────────────────────────────
        ttk.Label(f, text="Match\nPattern:").grid(
            row=4, column=0, sticky="nw", pady=4
        )
        pat_frame = ttk.Frame(f)
        pat_frame.grid(
            row=4, column=1, columnspan=2, sticky="ew", pady=4, padx=(8, 0)
        )
        self._preset = ttk.Combobox(
            pat_frame, values=[], state="readonly", width=44
        )
        self._refresh_preset_values()
        self._preset.set(self._NONE_LABEL)
        self._preset.pack(fill="x", pady=(0, 3))
        self._preset.bind("<<ComboboxSelected>>", self._on_preset_change)

        entry_row = ttk.Frame(pat_frame)
        entry_row.pack(fill="x", pady=(0, 2))
        self._pattern = ttk.Entry(entry_row, width=40)
        self._pattern.pack(side="left", fill="x", expand=True)
        ttk.Button(
            entry_row,
            text="\U0001f4be Save as Preset",
            command=self._on_save_preset,
        ).pack(side="left", padx=(4, 0))
        self._del_preset_btn = ttk.Button(
            entry_row,
            text="\U0001f5d1 Delete Preset",
            command=self._on_delete_preset,
            state="disabled",
        )
        self._del_preset_btn.pack(side="left", padx=(4, 0))

        help_frame = ttk.LabelFrame(
            pat_frame, text=" How it works ", padding=(8, 4)
        )
        help_frame.pack(fill="x", pady=(6, 0))
        help_text = (
            "\u2022 Leave blank \u2192 the full post title + body is searched.\n"
            "\u2022 Enter a regex \u2192 only the text captured by group\xa01 ( \u2026 ) is searched.\n"
            "  Useful when posts have a structured format, e.g. [H]\xa0have\xa0[W]\xa0want \u2014\n"
            "  set the pattern so group\xa01 captures only the [H] section.\n"
            "\u2022 Matching is case-insensitive. Monitor terms are plain keywords\n"
            "  (no regex) checked as substrings of whatever text is extracted.\n"
            "\u2022 Example: \\[H\\](.+?)(?=\\[W\\]|$) extracts everything after [H]\n"
            "  and before [W], so only items for sale are matched."
        )
        ttk.Label(
            help_frame,
            text=help_text,
            foreground="#888",
            font=("TkDefaultFont", 8),
            justify="left",
            wraplength=380,
        ).pack(anchor="w")

        sep2 = ttk.Separator(f, orient="horizontal")
        sep2.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=6, column=0, columnspan=3, pady=(10, 0), sticky="e")
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(
            side="right"
        )
        btn_text = "Save" if self._initial else "Add"
        ttk.Button(btn_frame, text=btn_text, command=self._submit).pack(
            side="right", padx=(0, 6)
        )

        f.columnconfigure(1, weight=1)
        if self._initial:
            self._name.insert(0, self._initial.get("name", ""))
            self._url.insert(0, self._initial.get("url", ""))
            self._type.set(self._initial.get("type", "reddit"))
            stored_pattern = self._initial.get("match_pattern", "")
            if stored_pattern:
                self._pattern.insert(0, stored_pattern)
                for label, regex in self._all_presets().items():
                    if regex == stored_pattern:
                        self._preset.set(label)
                        break
        self._name.focus_set()
        self.bind("<Return>", lambda _: self._submit())
        self.bind("<Escape>", lambda _: self.destroy())

    def _on_preset_change(self, _event=None) -> None:
        label = self._preset.get()
        if label in (self._BUILTIN_SEP, self._CUSTOM_SEP):
            self._preset.set(self._NONE_LABEL)
            self._pattern.delete(0, "end")
            self._del_preset_btn.config(state="disabled")
            return
        pattern = self._all_presets().get(label, "")
        self._pattern.delete(0, "end")
        if pattern:
            self._pattern.insert(0, pattern)
        user_presets = self._get_config().get("match_patterns", {})
        self._del_preset_btn.config(
            state="normal" if label in user_presets else "disabled"
        )

    def _on_delete_preset(self) -> None:
        label = self._preset.get()
        config = self._get_config()
        user_presets = config.get("match_patterns", {})
        if label not in user_presets:
            return
        if not messagebox.askyesno(
            "Delete Preset", f'Delete preset "{label}"?', parent=self
        ):
            return
        del user_presets[label]
        self._save_config(config)
        self._refresh_preset_values()
        self._preset.set(self._NONE_LABEL)
        self._pattern.delete(0, "end")
        self._del_preset_btn.config(state="disabled")

    def _on_save_preset(self) -> None:
        from tkinter.simpledialog import askstring

        pattern = self._pattern.get().strip()
        if not pattern:
            messagebox.showwarning(
                "Save Preset", "Enter a pattern first.", parent=self
            )
            return
        name = askstring("Save Preset", "Preset name:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        from watcher import PRESET_PATTERNS

        if name in PRESET_PATTERNS:
            messagebox.showerror(
                "Save Preset",
                f'"{name}" is a built-in preset name and cannot be overwritten.',
                parent=self,
            )
            return
        config = self._get_config()
        config.setdefault("match_patterns", {})[name] = pattern
        self._save_config(config)
        self._refresh_preset_values()
        self._preset.set(name)

    def _submit(self) -> None:
        name = self._name.get().strip()
        url = self._url.get().strip()
        if not name or not url:
            return
        self.result = {
            "name": name,
            "url": url,
            "type": self._type.get(),
            "match_pattern": self._pattern.get().strip(),
        }
        self.destroy()


class AddMonitorDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Widget,
        feed_names: list[str],
        initial: dict | None = None,
    ) -> None:
        super().__init__(parent)
        self.withdraw()
        self._initial = initial
        self.title("Edit Monitor" if initial else "Add Monitor")
        self.resizable(False, False)
        self.grab_set()
        apply_dialog_icon(self)
        self.result: Optional[
            tuple[str, list[str], Optional[float], list[str]]
        ] = None
        self._feed_names = feed_names
        self._build()
        _center_on_parent(self, parent)

    def _build(self) -> None:
        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Name:").grid(row=0, column=0, sticky="w", pady=4)
        self._name = ttk.Entry(f, width=36)
        self._name.grid(row=0, column=1, sticky="ew", pady=4, padx=(8, 0))

        ttk.Label(f, text="Terms\n(comma-separated):").grid(
            row=1, column=0, sticky="w", pady=4
        )
        self._terms = ttk.Entry(f, width=36)
        self._terms.grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 0))
        ttk.Label(
            f, text='e.g. "RTX 4080, RX 7900 XT"', foreground="#888"
        ).grid(row=2, column=1, sticky="w", padx=(8, 0))
        ttk.Label(
            f,
            text="Each term is a plain keyword. A post matches if any one term\n"
            "appears anywhere in the searched text (case-insensitive).",
            foreground="#888",
            font=("TkDefaultFont", 8),
            justify="left",
        ).grid(row=3, column=1, sticky="w", padx=(8, 0), pady=(0, 4))

        ttk.Label(f, text="Max Price ($):").grid(
            row=4, column=0, sticky="w", pady=4
        )
        price_row = ttk.Frame(f)
        price_row.grid(row=4, column=1, sticky="w", pady=4, padx=(8, 0))
        self._price = ttk.Entry(price_row, width=10)
        self._price.pack(side="left")
        ttk.Label(
            price_row, text="  (leave empty = any price)", foreground="#888"
        ).pack(side="left")

        ttk.Label(f, text="Feeds:").grid(row=5, column=0, sticky="nw", pady=6)
        feed_frame = ttk.LabelFrame(f, text="  apply to  ", padding=6)
        feed_frame.grid(row=5, column=1, sticky="ew", pady=4, padx=(8, 0))
        self._feed_vars: dict[str, tk.BooleanVar] = {}
        for name in self._feed_names:
            var = tk.BooleanVar(value=True)
            self._feed_vars[name] = var
            ttk.Checkbutton(feed_frame, text=name, variable=var).pack(
                anchor="w"
            )
        if not self._feed_names:
            ttk.Label(
                feed_frame, text="(no feeds configured yet)", foreground="#888"
            ).pack()

        sep = ttk.Separator(f, orient="horizontal")
        sep.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=(10, 0), sticky="e")
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(
            side="right"
        )
        btn_text = "Save" if self._initial else "Add"
        ttk.Button(btn_frame, text=btn_text, command=self._submit).pack(
            side="right", padx=(0, 6)
        )

        f.columnconfigure(1, weight=1)
        if self._initial:
            self._name.insert(0, self._initial.get("name", ""))
            self._terms.insert(0, ", ".join(self._initial.get("terms", [])))
            mp = self._initial.get("max_price")
            if mp is not None:
                self._price.insert(0, str(mp))
            selected = set(self._initial.get("feeds", []))
            for fname, var in self._feed_vars.items():
                var.set(fname in selected if selected else True)
        self._name.focus_set()
        self.bind("<Escape>", lambda _: self.destroy())

    def _submit(self) -> None:
        name = self._name.get().strip()
        if not name:
            return
        terms = [t.strip() for t in self._terms.get().split(",") if t.strip()]
        max_price: Optional[float] = None
        price_raw = self._price.get().strip()
        if price_raw:
            try:
                max_price = float(price_raw)
            except ValueError:
                self._price.config(foreground="red")
                return
        selected_feeds = [n for n, v in self._feed_vars.items() if v.get()]
        self.result = (name, terms, max_price, selected_feeds)
        self.destroy()


class HtmlRenderer(HTMLParser):
    """Parse HTML into a tk.Text widget, preserving formatting and making links clickable."""

    def __init__(self, text_widget: tk.Text) -> None:
        super().__init__(convert_charrefs=True)
        self._w = text_widget
        self._active_tags: list[str] = []
        self._list_stack: list[list] = (
            []
        )  # each item: [type("ul"|"ol"), counter]
        self._link_counter = 0
        self._current_link_tag = ""
        self._in_pre = False
        self._setup_static_tags()

    def _setup_static_tags(self) -> None:
        self._w.tag_configure("bold", font=("TkDefaultFont", 9, "bold"))
        self._w.tag_configure("italic", font=("TkDefaultFont", 9, "italic"))
        self._w.tag_configure(
            "code", font=("Consolas", 9), background="#f0f0f0"
        )
        self._w.tag_configure(
            "blockquote",
            foreground="#555555",
            font=("TkDefaultFont", 9, "italic"),
            lmargin1=20,
            lmargin2=20,
        )
        self._w.tag_configure("h1", font=("TkDefaultFont", 13, "bold"))
        self._w.tag_configure("h2", font=("TkDefaultFont", 11, "bold"))
        self._w.tag_configure("h3", font=("TkDefaultFont", 10, "bold"))
        self._w.tag_configure("del_text", overstrike=True)
        self._w.tag_configure("sup", offset=4, font=("TkDefaultFont", 7))

    def render(self, html: str) -> None:
        """Clear the widget and render *html* into it."""
        self._w.config(state="normal")
        self._w.delete("1.0", "end")
        # Remove old per-render link tags so bindings don't leak
        for tag in list(self._w.tag_names()):
            if tag.startswith("link_"):
                self._w.tag_delete(tag)
        self._link_counter = 0
        self._active_tags.clear()
        self._list_stack.clear()
        self._current_link_tag = ""
        self._in_pre = False
        self.reset()
        self.feed(html or "(no body text)")
        self._w.config(state="disabled")
        self._w.yview_moveto(0)

    # ── Internal helpers ───────────────────────────────────────────────────

    def _ensure_newline(self) -> None:
        content = self._w.get("1.0", "end-1c")
        if content and not content.endswith("\n"):
            self._w.insert("end", "\n")

    def _pop_tag(self, t: str) -> None:
        for i in range(len(self._active_tags) - 1, -1, -1):
            if self._active_tags[i] == t:
                self._active_tags.pop(i)
                return

    def _current_tags(self) -> tuple:
        seen: set[str] = set()
        result = []
        for t in self._active_tags:
            if t not in seen:
                seen.add(t)
                result.append(t)
        return tuple(result)

    # ── HTMLParser callbacks ───────────────────────────────────────────────

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attrs_d = dict(attrs)

        if tag in ("b", "strong"):
            self._active_tags.append("bold")
        elif tag in ("i", "em"):
            self._active_tags.append("italic")
        elif tag in ("del", "s", "strike"):
            self._active_tags.append("del_text")
        elif tag == "sup":
            self._active_tags.append("sup")
        elif tag in ("code", "tt"):
            self._active_tags.append("code")
        elif tag == "pre":
            self._in_pre = True
            self._ensure_newline()
            self._active_tags.append("code")
        elif tag == "a":
            href = attrs_d.get("href", "")
            if href:
                self._link_counter += 1
                ltag = f"link_{self._link_counter}"
                self._w.tag_configure(
                    ltag, foreground="#0066cc", underline=True
                )
                self._w.tag_bind(
                    ltag, "<Button-1>", lambda e, u=href: webbrowser.open(u)
                )
                self._w.tag_bind(
                    ltag, "<Enter>", lambda e: self._w.config(cursor="hand2")
                )
                self._w.tag_bind(
                    ltag, "<Leave>", lambda e: self._w.config(cursor="")
                )
                self._active_tags.append(ltag)
                self._current_link_tag = ltag
        elif tag in ("p", "div"):
            self._ensure_newline()
        elif tag == "br":
            self._w.insert("end", "\n")
        elif tag in ("ul", "ol"):
            self._list_stack.append([tag, 0])
            self._ensure_newline()
        elif tag == "li":
            self._ensure_newline()
            if self._list_stack:
                if self._list_stack[-1][0] == "ol":
                    self._list_stack[-1][1] += 1
                    bullet = f"  {self._list_stack[-1][1]}. "
                else:
                    bullet = "  • "
            else:
                bullet = "  • "
            self._w.insert("end", bullet)
        elif tag == "blockquote":
            self._ensure_newline()
            self._active_tags.append("blockquote")
        elif tag in ("h1", "h2", "h3"):
            self._ensure_newline()
            self._active_tags.append(tag)
        elif tag in ("h4", "h5", "h6"):
            self._ensure_newline()
            self._active_tags.append("bold")
        elif tag == "hr":
            self._ensure_newline()
            self._w.insert("end", "─" * 50 + "\n")
        elif tag == "tr":
            self._ensure_newline()
        elif tag in ("td", "th"):
            self._w.insert("end", "  ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("b", "strong"):
            self._pop_tag("bold")
        elif tag in ("i", "em"):
            self._pop_tag("italic")
        elif tag in ("del", "s", "strike"):
            self._pop_tag("del_text")
        elif tag == "sup":
            self._pop_tag("sup")
        elif tag in ("code", "tt"):
            self._pop_tag("code")
        elif tag == "pre":
            self._in_pre = False
            self._pop_tag("code")
            self._ensure_newline()
        elif tag == "a":
            if self._current_link_tag:
                self._pop_tag(self._current_link_tag)
                self._current_link_tag = ""
        elif tag in ("p", "div"):
            self._ensure_newline()
        elif tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
            self._ensure_newline()
        elif tag == "li":
            self._ensure_newline()
        elif tag == "blockquote":
            self._pop_tag("blockquote")
            self._ensure_newline()
        elif tag in ("h1", "h2", "h3"):
            self._pop_tag(tag)
            self._ensure_newline()
        elif tag in ("h4", "h5", "h6"):
            self._pop_tag("bold")
            self._ensure_newline()
        elif tag == "tr":
            self._ensure_newline()
        elif tag in ("td", "th"):
            self._w.insert("end", "  |")

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if not self._in_pre:
            data = re.sub(r"[ \t\r\n]+", " ", data)
            # Don't insert a lone space at the very start or right after a newline
            if data == " ":
                content = self._w.get("1.0", "end-1c")
                if not content or content.endswith("\n"):
                    return
        if data:
            self._w.insert("end", data, self._current_tags())


class FeedPreviewDialog(tk.Toplevel):
    """
    Shows the latest items from a single feed.

    The detail panel is hidden by default.  Selecting a post auto-shows it
    (first time only).  Once the user hides it via the ◀ Hide button, it
    stays hidden until they explicitly press "Show Details ▶".
    """

    COLUMNS = ("published", "title")
    HEADINGS = {"published": "Published", "title": "Title"}
    WIDTHS = {"published": 155, "title": 380}

    # Narrow width used when the detail pane is hidden
    _WIDTH_LIST_ONLY = 620
    # Width used when the detail pane is visible
    _WIDTH_WITH_DETAIL = 1200

    def __init__(
        self, parent: tk.Widget, feed_cfg: dict, user_agent: str, conn=None
    ) -> None:
        super().__init__(parent)
        self.withdraw()
        self.title(f"Preview — {feed_cfg['name']}")
        self.geometry(f"{self._WIDTH_LIST_ONLY}x560")
        self.minsize(500, 400)
        self.grab_set()
        apply_dialog_icon(self)
        self._feed_cfg = feed_cfg
        self._user_agent = user_agent
        self._conn = conn
        self._links: dict[str, str] = {}
        self._summaries: dict[str, str] = {}
        # True after the user explicitly hides the panel; resets on Show click
        self._panel_locked_hidden: bool = False
        # Tracks whether the detail pane is currently in the PanedWindow
        self._detail_pane_visible: bool = False
        self._build()
        _center_on_parent(self, parent)
        self.config(cursor="wait")
        self.after(80, self._load)

    # ── Build UI ───────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── Toolbar ────────────────────────────────────────────────────────
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=6, pady=(6, 0))

        self._status_var = tk.StringVar(value="Fetching…")
        ttk.Label(
            toolbar, textvariable=self._status_var, foreground="#555"
        ).pack(side="left")
        ttk.Button(toolbar, text="Close", command=self.destroy).pack(
            side="right"
        )
        ttk.Button(
            toolbar, text="Open in Browser", command=self._open_selected
        ).pack(side="right", padx=(0, 4))
        self._show_btn = ttk.Button(
            toolbar, text="Show Details ▶", command=self._show_panel
        )
        self._show_btn.pack(side="right", padx=(0, 4))

        # ── PanedWindow ────────────────────────────────────────────────────
        self._pane = ttk.PanedWindow(self, orient="horizontal")
        self._pane.pack(fill="both", expand=True, padx=6, pady=6)

        # Left pane — post list (always present)
        list_frame = ttk.Frame(self._pane)
        self._pane.add(list_frame, weight=2)

        self._tree = ttk.Treeview(
            list_frame,
            columns=self.COLUMNS,
            show="headings",
            selectmode="browse",
        )
        for col in self.COLUMNS:
            self._tree.heading(col, text=self.HEADINGS[col])
            self._tree.column(
                col, width=self.WIDTHS[col], stretch=(col == "title")
            )
        vsb = ttk.Scrollbar(
            list_frame, orient="vertical", command=self._tree.yview
        )
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", self._open_link)

        # Right pane — post detail (built here but NOT added to pane yet)
        self._detail_frame = ttk.Frame(self._pane)

        # Detail header row: title + Hide button
        detail_header = ttk.Frame(self._detail_frame)
        detail_header.pack(fill="x", padx=8, pady=(6, 0))

        self._detail_title = tk.StringVar(value="")
        ttk.Label(
            detail_header,
            textvariable=self._detail_title,
            font=("TkDefaultFont", 10, "bold"),
            wraplength=400,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            detail_header, text="◀ Hide", command=self._hide_panel
        ).pack(side="right")

        self._detail_link_var = tk.StringVar()
        link_lbl = ttk.Label(
            self._detail_frame,
            textvariable=self._detail_link_var,
            foreground="#0066cc",
            cursor="hand2",
            wraplength=480,
            justify="left",
        )
        link_lbl.pack(anchor="w", padx=8, pady=(2, 0))
        link_lbl.bind("<Button-1>", self._open_selected)

        ttk.Separator(self._detail_frame, orient="horizontal").pack(
            fill="x", padx=8, pady=6
        )

        body_frame = ttk.Frame(self._detail_frame)
        body_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._body_text = tk.Text(
            body_frame,
            wrap="word",
            font=("TkDefaultFont", 9),
            relief="flat",
            state="disabled",
            bg=self.cget("bg"),
        )
        body_vsb = ttk.Scrollbar(
            body_frame, orient="vertical", command=self._body_text.yview
        )
        self._body_text.configure(yscrollcommand=body_vsb.set)
        self._body_text.pack(side="left", fill="both", expand=True)
        body_vsb.pack(side="right", fill="y")

        self._html_renderer = HtmlRenderer(self._body_text)

        ttk.Label(
            self,
            text="Double-click a row to open in browser",
            foreground="#888",
        ).pack(pady=(0, 4))

    # ── Panel show / hide ──────────────────────────────────────────────────

    def _show_panel(self) -> None:
        """Explicitly show the detail panel (Show Details button)."""
        self._panel_locked_hidden = False
        self._add_detail_pane()
        # Render whichever row is currently selected
        item = self._tree.focus()
        if item:
            self._render_item(item)
        self._show_btn.config(state="disabled")

    def _hide_panel(self) -> None:
        """Hide button inside the detail pane."""
        self._panel_locked_hidden = True
        self._remove_detail_pane()
        self._show_btn.config(state="normal")

    def _add_detail_pane(self) -> None:
        if not self._detail_pane_visible:
            self._pane.add(self._detail_frame, weight=1)
            self._detail_pane_visible = True
            # Widen the window so both panes have breathing room
            h = self.winfo_height()
            self.geometry(f"{self._WIDTH_WITH_DETAIL}x{h}")

    def _remove_detail_pane(self) -> None:
        if self._detail_pane_visible:
            self._pane.forget(self._detail_frame)
            self._detail_pane_visible = False
            # Shrink back to list-only width
            h = self.winfo_height()
            self.geometry(f"{self._WIDTH_LIST_ONLY}x{h}")

    # ── Render helpers ─────────────────────────────────────────────────────

    def _render_item(self, item: str) -> None:
        values = self._tree.item(item)["values"]
        title = values[1] if len(values) > 1 else ""
        link = self._links.get(item, "")
        summary = self._summaries.get(item, "")
        self._detail_title.set(title)
        self._detail_link_var.set(link)
        self._html_renderer.render(summary)

    # ── Event handlers ─────────────────────────────────────────────────────

    def _on_select(self, _event) -> None:
        item = self._tree.focus()
        if not item:
            return
        if self._panel_locked_hidden:
            # User explicitly hid the panel — respect that, do nothing
            return
        # Auto-show on first selection or update if already visible
        if not self._detail_pane_visible:
            self._add_detail_pane()
            self._show_btn.config(state="disabled")
        self._render_item(item)

    def _load(self) -> None:
        from watcher import fetch_feed
        from database import is_seen, mark_seen

        entries = fetch_feed(self._feed_cfg, self._user_agent)
        self.config(cursor="")
        for e in entries:
            pub_str = fmt_dt(e["published"])
            iid = self._tree.insert("", "end", values=(pub_str, e["title"]))
            self._links[iid] = e["link"]
            self._summaries[iid] = (
                e.get("summary_html") or e.get("summary") or ""
            )
            # Persist into DB so subsequent checks don't re-evaluate these
            if self._conn is not None:
                item_id = e.get("id") or e["link"]
                if item_id and not is_seen(self._conn, item_id):
                    mark_seen(
                        self._conn,
                        item_id,
                        self._feed_cfg["name"],
                        e["title"],
                        e["link"],
                        published=e.get("published", ""),
                    )
        self._status_var.set(
            f"{len(entries)} items  —  select to preview · double-click to open"
        )

    def _open_selected(self, _event=None) -> None:
        item = self._tree.focus()
        if item and item in self._links:
            webbrowser.open(self._links[item])

    def _open_link(self, _event) -> None:
        self._open_selected()


class DealPreviewDialog(tk.Toplevel):
    """Show the body of a single deal post inline.

    Accepts a *deal* dict with keys:
      title, url, monitor, feed, price_str, discovered, published,
      summary_html (optional — pre-fetched HTML body).

    If *summary_html* is empty the dialog fetches the post's ``.rss``
    URL on a background thread so the UI stays responsive.
    """

    def __init__(self, parent: tk.Widget, deal: dict, user_agent: str) -> None:
        super().__init__(parent)
        self.withdraw()
        short_title = deal.get("title", "Deal")[:70]
        self.title(f"Preview — {short_title}")
        self.geometry("860x580")
        self.minsize(500, 400)
        self.resizable(True, True)
        self.grab_set()
        apply_dialog_icon(self)
        self._deal = deal
        self._user_agent = user_agent
        self._build()
        _center_on_parent(self, parent)
        # Kick off content load after window is visible
        self.after(80, self._load)

    # ── Build ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Header bar
        hdr = ttk.Frame(self)
        hdr.pack(fill="x", padx=10, pady=(8, 0))

        title_text = self._deal.get("title", "")
        ttk.Label(
            hdr,
            text=title_text,
            font=("TkDefaultFont", 10, "bold"),
            wraplength=700,
            justify="left",
        ).pack(anchor="w")

        # Meta row: monitor · feed · price · dates
        meta_parts = []
        if self._deal.get("monitor"):
            meta_parts.append(f"Monitor: {self._deal['monitor']}")
        if self._deal.get("feed"):
            meta_parts.append(f"Feed: {self._deal['feed']}")
        if self._deal.get("price_str"):
            meta_parts.append(f"Price: {self._deal['price_str']}")
        if self._deal.get("discovered"):
            meta_parts.append(f"Found: {self._deal['discovered']}")
        if self._deal.get("published"):
            meta_parts.append(f"Published: {self._deal['published']}")

        if meta_parts:
            ttk.Label(
                hdr,
                text="  ·  ".join(meta_parts),
                foreground="#888",
                font=("TkDefaultFont", 8),
            ).pack(anchor="w", pady=(2, 0))

        # Clickable URL
        url = self._deal.get("url", "")
        if url:
            link_lbl = ttk.Label(
                hdr,
                text=url,
                foreground="#0066cc",
                cursor="hand2",
                font=("TkDefaultFont", 8),
                wraplength=700,
            )
            link_lbl.pack(anchor="w", pady=(2, 0))
            link_lbl.bind("<Button-1>", lambda _e: webbrowser.open(url))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=6, pady=6)

        # Status label
        self._status_var = tk.StringVar(value="Loading…")
        ttk.Label(self, textvariable=self._status_var, foreground="#555").pack(
            anchor="w", padx=10
        )

        # Body text area
        body_frame = ttk.Frame(self)
        body_frame.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        self._body_text = tk.Text(
            body_frame,
            wrap="word",
            font=("TkDefaultFont", 9),
            relief="flat",
            state="disabled",
            bg=self.cget("bg"),
        )
        vsb = ttk.Scrollbar(
            body_frame, orient="vertical", command=self._body_text.yview
        )
        self._body_text.configure(yscrollcommand=vsb.set)
        self._body_text.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._html_renderer = HtmlRenderer(self._body_text)

        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=(4, 8))
        ttk.Button(toolbar, text="Close", command=self.destroy).pack(
            side="right"
        )
        ttk.Button(
            toolbar,
            text="🌐 Open in Browser",
            command=lambda: webbrowser.open(url) if url else None,
        ).pack(side="right", padx=(0, 6))

        self.bind("<Escape>", lambda _: self.destroy())

    # ── Load ───────────────────────────────────────────────────────────────

    def _load(self) -> None:
        import threading

        html = self._deal.get("summary_html", "")
        if html:
            self._html_renderer.render(html)
            self._status_var.set("Loaded from cache.")
            return

        # Fetch in a background thread so the UI stays responsive
        self._status_var.set("Fetching post content…")
        self.config(cursor="wait")

        def _fetch() -> None:
            import requests
            import feedparser

            url = self._deal.get("url", "")
            result_html = ""
            try:
                rss_url = url.rstrip("/") + ".rss"
                resp = requests.get(
                    rss_url,
                    headers={"User-Agent": self._user_agent},
                    timeout=15,
                )
                resp.raise_for_status()
                parsed = feedparser.parse(resp.content)
                if parsed.entries:
                    raw = getattr(parsed.entries[0], "summary", "") or ""
                    result_html = raw
            except Exception as exc:
                result_html = f"<p><em>Could not load preview: {exc}</em></p>"

            # Schedule UI update back on the main thread
            try:
                self.after(0, lambda: self._on_loaded(result_html))
            except tk.TclError:
                pass  # dialog was closed before fetch finished

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_loaded(self, html: str) -> None:
        self._html_renderer.render(
            html or "<p>(No body content available.)</p>"
        )
        self._status_var.set(
            "Loaded — double-click links to open · close when done"
        )
        self.config(cursor="")
