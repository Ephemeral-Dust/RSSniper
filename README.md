# RSSniper

A Python desktop application that monitors RSS feeds for posts matching your keywords and optional price thresholds. When a deal is found you get a desktop notification and it appears in the GUI dashboard.

---

## Features

- **GUI dashboard** — tabbed interface (Deals, Feeds, Monitors, Log) built with tkinter; no browser required
- **Dark / light / system theme** — Sun Valley (sv-ttk) theme with dark title bar; switchable per-session via Settings
- **Right-click context menus** — on Deals, Feeds, and Monitors tabs for quick actions (open, copy, edit, remove, dismiss)
- **System tray support** — minimise to system tray via the **⬇ Tray** button; each tab has its own **⚡ Check Now** and **⬇ Tray** buttons
- **Background polling** — checks feeds on a configurable interval (default 15 min) in a daemon thread
- **Keyword + price matching** — monitors trigger on any matching term; optionally cap at a max price
- **Context-aware price extraction** — prices are matched to the line containing the keyword, avoiding mis-attribution in multi-item posts
- **Automatic feed pagination** — transparently pages through Reddit's `.rss` endpoint up to a configurable lookback window (default 3 days); non-Reddit feeds fetch a single page and stop gracefully
- **Feed preview** — inline HTML rendering of post bodies with clickable links, directly inside the app
- **Feed match patterns** — optional per-feed regex filters (built-in presets or custom) that restrict which part of a post is matched against monitors; patterns act as filters — a post that doesn't match the pattern is excluded entirely
- **Persistent history** — SQLite database tracks seen items and matched deals so duplicates are never re-alerted across restarts
- **Pattern re-evaluation** — changing a feed's match pattern immediately re-evaluates all stored history; deals that no longer match are removed and newly matching ones are added
- **Published date tracking** — post publish times are stored and displayed alongside the discovered time
- **New vs Historical status** — deals found in the current check are flagged 🆕 New; deals loaded from a previous session are 📦 Historical
- **Default sort: newest first** — Deals tab opens sorted by Discovered descending; sort order persists through previews and filter changes
- **Monitor enable/disable** — disabling a monitor immediately removes its deals from the Deals tab; re-enabling re-scans stored history and restores matching deals
- **Desktop notifications** — Windows toast notifications via plyer (gracefully degrades if unavailable)
- **Configuration import / export** — export feeds, monitors, and regex presets to a portable JSON file; import with conflict-resolution diff dialog (Overwrite / Skip / Skip All / Cancel)
- **Detailed logging** — Log tab with level filter (DEBUG / INFO / WARNING / ERROR) that filters in real time without discarding buffered messages; optional file logging with automatic rotation
- **Settings dialog** — all options editable in-app and persisted to `config.json`
- **CLI mode** — headless operation for servers or scripting

---

## Requirements

- Python 3.10+
- Windows (tested); Linux/macOS should work but desktop notifications may vary

```
feedparser>=6.0.11
requests>=2.31.0
schedule>=1.2.0
rich>=13.0.0
plyer>=2.1.0
sv-ttk>=2.6.0
pystray>=0.19.0
Pillow>=10.0.0
```

---

## Installation

```bash
git clone <repo>
cd RSSniper
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

---

## Usage

### GUI (default)

```bash
python main.py
```

The app opens with four tabs:

| Tab          | Purpose                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| **Deals**    | Live and historical matched deals; double-click a row to open the post   |
| **Feeds**    | Add, edit, remove, and preview RSS feeds; set per-feed match patterns    |
| **Monitors** | Configure keyword/price rules; enable or disable each one                |
| **Log**      | Live watcher activity with colour-coded levels and optional file logging |

Every tab toolbar has **⚡ Check Now** (trigger an immediate check) and **⬇ Tray** (minimise to system tray).

Use **Settings → Settings…** to adjust all configuration options without editing files.
Use **Settings → Export…** / **Settings → Import…** to back up or migrate your configuration.

### CLI

```bash
python main.py watch          # Continuous polling (respects check_interval_minutes)
python main.py check          # Single check then exit
python main.py list           # Print all feeds and monitors
python main.py add-feed NAME URL
python main.py add-monitor NAME --terms TERM1 TERM2 [--max-price 400] [--feeds FEED1 FEED2]
```

---

## Configuration

`config.json` is created automatically on first run at `%APPDATA%\RSSniper\config.json` (frozen exe) or the project root (dev mode). All values can be changed via the Settings dialog or by editing the file directly.

| Key                               | Default        | Description                                           |
| --------------------------------- | -------------- | ----------------------------------------------------- |
| `check_interval_minutes`          | `15`           | How often the background scheduler polls feeds        |
| `check_on_startup`                | `true`         | Run a check immediately when the app launches         |
| `max_lookback_days`               | `3`            | How far back to page through feeds                    |
| `max_entries_per_feed`            | `1000`         | Hard cap on entries fetched per feed per check        |
| `request_timeout_seconds`         | `15`           | HTTP request timeout                                  |
| `page_delay_seconds`              | `0.75`         | Delay between paginated requests (be a good citizen)  |
| `user_agent`                      | `RSSniper/1.0` | User-Agent header sent to feeds                       |
| `notifications.desktop`           | `true`         | Show Windows desktop toast on new deal                |
| `notifications.console`           | `true`         | Append matches to the Log tab                         |
| `notifications.notify_historical` | `false`        | Show notifications for DB-scan matches on startup     |
| `logging.level_filter`            | `"DEBUG"`      | Minimum log level shown in the Log tab                |
| `logging.save_to_file`            | `false`        | Write logs to `logs/rdw.log` with rotation            |
| `theme`                           | `"dark"`       | GUI colour scheme: `"dark"`, `"light"`, or `"system"` |

### Monitors

Each monitor has:

| Field       | Required | Description                                                                      |
| ----------- | -------- | -------------------------------------------------------------------------------- |
| `name`      | Yes      | Display name                                                                     |
| `terms`     | Yes      | List of keywords — **any one** matching triggers the monitor (OR logic)          |
| `max_price` | No       | If set, the post must contain a price on the matched line at or below this value |
| `feeds`     | No       | Limit to specific feed names; omit to check all feeds                            |
| `enabled`   | No       | `true` by default; set `false` to pause without deleting                         |

### Feed Match Patterns

Feeds can have an optional regex pattern that filters which part of a post is tested against monitors:

- **No pattern** — the full post title + body is used (default behaviour)
- **Pattern set** — only the text captured by the pattern is passed to monitors; posts with no match are skipped entirely
- Built-in presets (e.g. "Price line") and user-defined named presets are available from the pattern combobox in the Feeds tab

Changing a pattern immediately re-evaluates all stored historical posts for that feed.

---

## How Matching Works

1. Each enabled monitor is tested against the post title + body (or the pattern-extracted text, if a feed pattern is set).
2. If any `term` is found (case-insensitive), the post is a candidate.
3. Prices (e.g. `$600`, `$1,200.00`) are extracted **from the same line as the matched term first**. This handles multi-item posts where each item has its own price on its own line.
4. If no price is on that line, the global minimum price in the post is used as a fallback.
5. If `max_price` is configured, the extracted price must be ≤ that value; if no price is found the post still matches (price unknown).
6. On a match, a deal is recorded in the database and the `on_match` callback fires (notification + UI update).

---

## Log Tab

The Log tab shows real-time watcher activity with colour-coded severity levels:

| Level     | Colour | Typical content                       |
| --------- | ------ | ------------------------------------- |
| `DEBUG`   | Grey   | Per-feed fetch progress, entry counts |
| `INFO`    | White  | Check start/end, deal matches         |
| `WARNING` | Orange | Fetch failures, skipped items         |
| `ERROR`   | Red    | Unhandled exceptions, DB errors       |

- The **Level** combobox filters the displayed log in real time. Buffered messages are not discarded — switching back to DEBUG restores full history.
- **Save log to file** writes to `%APPDATA%\RSSniper\logs\rdw.log`, rotating at 2 MB with 3 backups kept. Enable this before reproducing a bug to capture a log for support.
- Both settings persist across sessions and can also be configured in **Settings → Logging**.

---

## Import / Export

Export and import your configuration via **Settings → Export…** / **Settings → Import…**.

**Export** — choose which sections to include (Feeds, Monitors, Regex Presets) and save to a `.json` file.

**Import** — select a previously exported file. If a feed or monitor with the same name already exists, a diff dialog shows the differences and lets you choose:

| Action        | Effect                                                 |
| ------------- | ------------------------------------------------------ |
| Overwrite     | Replace the existing entry with the imported one       |
| Skip          | Keep the existing entry, skip this imported item       |
| Skip All      | Skip all remaining conflicts without further prompting |
| Cancel Import | Abort — nothing is saved                               |

---

## Database

SQLite database at `%APPDATA%\RSSniper\seen_items.db` (frozen) or project root (dev). Three tables:

| Table          | Purpose                                                              |
| -------------- | -------------------------------------------------------------------- |
| `seen_items`   | Every post URL that has been fetched — prevents re-processing        |
| `feed_checks`  | Last-checked timestamp per feed — drives incremental fetching        |
| `deal_matches` | Every (post, monitor) match — drives the Deals tab and deduplication |

The database is append-only during normal operation. The **Clear** button on the Deals tab clears the UI only; the underlying records are kept so the next check remains incremental.

---

## Building the Executable

A single-file Windows exe can be built with PyInstaller. All data files (config, database, logs) are created automatically at runtime in `%APPDATA%\RSSniper` — nothing needs to be shipped alongside the exe.

**Prerequisites:** complete the [Installation](#installation) steps above.

```bash
# Install PyInstaller into the venv (one-time)
venv\Scripts\pip install pyinstaller

# Build
venv\Scripts\pyinstaller RSSniper.spec --clean
```

Output: `dist\RSSniper.exe` — no installer required.

**On first launch the exe will:**

1. Create `%APPDATA%\RSSniper\` if it does not exist
2. Write a default `config.json` with example feeds and monitors
3. Initialise `seen_items.db`

To rebuild after making code changes, run the `pyinstaller` command again.

---

## Limitations

- **Reddit rate limits** — Reddit throttles unauthenticated RSS requests. The `page_delay_seconds` setting adds a courtesy delay between paginated requests. Heavy usage may still hit limits.
- **Title-only DB scanning** — The startup re-scan (which checks already-seen posts against new or changed monitors/patterns) only has access to stored post titles, not bodies, because full HTML is not stored in the database. Price extraction may be less accurate for these historical items.
- **Multi-item post prices** — Contextual line-matching significantly improves accuracy, but posts with unusual formatting (price on a different line from the item name) may still extract the wrong price. The price is informational; always verify on the post.
- **No Reddit authentication** — Uses public `.rss` endpoints only. Private/NSFW subreddits and subreddits that block unauthenticated access are not supported.
- **Lookback window** — Only the last `max_lookback_days` of posts are checked. Deals older than that window will not appear even on first run.
- **Windows notifications** — Desktop notifications use `plyer` which relies on Windows Toast on Windows 10/11. Behaviour on older Windows or non-Windows platforms may vary.
