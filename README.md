# RedditDealWatcher

A Python desktop application that monitors Reddit RSS feeds for posts matching your keywords and optional price thresholds. When a deal is found you get a desktop notification and it appears in the GUI dashboard.

---

## Features

- **GUI dashboard** — tabbed interface (Deals, Feeds, Monitors, Log) built with tkinter; no browser required
- **Background polling** — checks feeds on a configurable interval (default 15 min) in a daemon thread
- **Keyword + price matching** — monitors trigger on any matching term; optionally cap at a max price
- **Context-aware price extraction** — prices are matched to the line containing the keyword, avoiding mis-attribution in multi-item posts
- **Paginated feed fetching** — pages back through Reddit's `.rss` endpoint up to a configurable lookback window (default 3 days)
- **Feed preview** — inline HTML rendering of post bodies with clickable links, directly inside the app
- **Persistent history** — SQLite database tracks seen items and matched deals so duplicates are never re-alerted across restarts
- **Published date tracking** — post publish times are stored and displayed alongside the discovered time
- **New vs Historical status** — deals found in the current check are flagged 🆕 New; deals loaded from a previous session are 📦 Historical
- **Desktop notifications** — Windows toast notifications via plyer (gracefully degrades if unavailable)
- **Settings dialog** — all options (poll interval, lookback window, network timeouts, notifications) are editable in-app and persisted to `config.json`
- **CLI mode** — headless operation for servers or scripting

---

## Requirements

- Python 3.10+
- Windows (tested), Linux/macOS should work but desktop notifications may vary

```
feedparser>=6.0.11
requests>=2.31.0
schedule>=1.2.0
rich>=13.0.0
plyer>=2.1.0
```

---

## Installation

```bash
git clone <repo>
cd RedditDealWatcher
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

| Tab          | Purpose                                                                |
| ------------ | ---------------------------------------------------------------------- |
| **Deals**    | Live and historical matched deals; double-click a row to open the post |
| **Feeds**    | Add, edit, remove, and preview RSS feeds                               |
| **Monitors** | Configure keyword/price rules; enable or disable each one              |
| **Log**      | Live watcher activity with color-coded log levels                      |

Use **⚡ Check Now** (toolbar or Watcher menu) to trigger an immediate check.
Use **Watcher → Settings…** to adjust all configuration options without editing files.

### CLI

```bash
python main.py watch          # Continuous polling (respects check_interval_minutes)
python main.py check          # Single check then exit
python main.py list           # Print all feeds and monitors
python main.py add-feed NAME URL [--type reddit|rss]
python main.py add-monitor NAME --terms TERM1 TERM2 [--max-price 400] [--feeds FEED1 FEED2]
```

---

## Configuration

`config.json` is created automatically on first run with sensible defaults. All values can be changed via the Settings dialog in the GUI or by editing the file directly.

| Key                               | Default                 | Description                                          |
| --------------------------------- | ----------------------- | ---------------------------------------------------- |
| `check_interval_minutes`          | `15`                    | How often the background scheduler polls feeds       |
| `check_on_startup`                | `true`                  | Run a check immediately when the app launches        |
| `max_lookback_days`               | `3`                     | How far back to page through feeds                   |
| `max_entries_per_feed`            | `1000`                  | Hard cap on entries fetched per feed per check       |
| `request_timeout_seconds`         | `15`                    | HTTP request timeout                                 |
| `page_delay_seconds`              | `0.75`                  | Delay between paginated requests (be a good citizen) |
| `user_agent`                      | `RedditDealWatcher/1.0` | User-Agent header sent to Reddit                     |
| `notifications.desktop`           | `true`                  | Show Windows desktop toast on new deal               |
| `notifications.console`           | `true`                  | Print matches to console in CLI mode                 |
| `notifications.notify_historical` | `false`                 | Show notifications for DB-scan matches on startup    |

### Monitors

Each monitor has:

| Field       | Required | Description                                                                      |
| ----------- | -------- | -------------------------------------------------------------------------------- |
| `name`      | Yes      | Display name                                                                     |
| `terms`     | Yes      | List of keywords — **any one** matching triggers the monitor (OR logic)          |
| `max_price` | No       | If set, the post must contain a price on the matched line at or below this value |
| `feeds`     | No       | Limit to specific feed names; omit to check all feeds                            |
| `enabled`   | No       | `true` by default; set `false` to pause without deleting                         |

---

## How Matching Works

1. Each enabled monitor is tested against the post title + body.
2. If any `term` is found (case-insensitive), the post is a candidate.
3. Prices (e.g. `$600`, `$1,200.00`) are extracted **from the same line as the matched term first**. This handles multi-item posts where each item has its own price on its own line.
4. If no price is on that line, the global minimum price in the post is used as a fallback.
5. If `max_price` is configured, the extracted price must be ≤ that value; if no price is found the post still matches (price unknown).
6. On a match, a deal is recorded in the database and the `on_match` callback fires (notification + UI update).

---

## Database

SQLite database at `seen_items.db` (project root). Three tables:

| Table          | Purpose                                                              |
| -------------- | -------------------------------------------------------------------- |
| `seen_items`   | Every post URL that has been fetched — prevents re-processing        |
| `feed_checks`  | Last-checked timestamp per feed — drives incremental fetching        |
| `deal_matches` | Every (post, monitor) match — drives the Deals tab and deduplication |

The database is **append-only during normal operation**. Clearing it via the GUI's Deals tab Clear button only clears the UI; the next check re-fetches only new content (incremental). To re-process history, the relevant tables need to be cleared directly.

---

## Building the Executable

A single-file Windows exe can be built with PyInstaller. All data files (config, database) are created automatically at runtime in `%APPDATA%\RedditDealWatcher` — nothing needs to be shipped alongside the exe.

**Prerequisites:** complete the [Installation](#installation) steps above so the venv and dependencies are in place.

```bash
# Install PyInstaller into the venv (one-time)
venv\Scripts\pip install pyinstaller

# Build
venv\Scripts\pyinstaller RedditDealWatcher.spec --clean
```

Output: `dist\RedditDealWatcher.exe` (~17 MB, no installer required).

**On first launch the exe will:**

1. Create `%APPDATA%\RedditDealWatcher\` if it does not exist
2. Write a default `config.json` with example feeds and monitors
3. Initialise `seen_items.db`

To rebuild after making code changes, run the `pyinstaller` command again.

---

## Limitations

- **Reddit rate limits** — Reddit throttles unauthenticated RSS requests. The `page_delay_seconds` setting adds a courtesy delay between paginated requests. Heavy usage may still hit limits.
- **Title-only DB scanning** — The `scan_seen_for_deals` function (which re-checks already-seen posts on startup) only has access to post titles, not bodies, because full post HTML is not stored in the database. Price extraction may be less accurate for these.
- **Multi-item post prices** — Contextual line-matching significantly improves accuracy, but posts with unusual formatting (prices on a different line from the item name) may still get the wrong price. The price is informational; always verify on the post.
- **No Reddit authentication** — Uses public `.rss` endpoints only. Private/NSFW subreddits and subreddits that block unauthenticated access are not supported.
- **Lookback window** — Only the last `max_lookback_days` of posts are checked. Deals older than that window will never appear even on first run.
- **Windows notifications** — Desktop notifications use `plyer` which relies on Windows Toast on Windows 10/11. Behavior on older Windows or non-Windows platforms may vary.
