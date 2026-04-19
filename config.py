import json
from pathlib import Path

CONFIG_FILE = Path("config.json")

DEFAULT_CONFIG: dict = {
    # ── Watcher ────────────────────────────────────────────────────────────────
    "check_interval_minutes": 15,
    "check_on_startup": True,
    # ── History ────────────────────────────────────────────────────────────────
    "max_lookback_days": 3,
    "max_entries_per_feed": 1000,
    # ── Network ────────────────────────────────────────────────────────────────
    "request_timeout_seconds": 15,
    "page_delay_seconds": 0.75,
    "feeds": [
        {
            "name": "r/deals",
            "url": "https://www.reddit.com/r/deals/.rss",
            "type": "reddit",
        },
        {
            "name": "r/buildapcsales",
            "url": "https://www.reddit.com/r/buildapcsales/.rss",
            "type": "reddit",
        },
        {
            "name": "r/frugalmalefashion",
            "url": "https://www.reddit.com/r/frugalmalefashion/.rss",
            "type": "reddit",
        },
        {
            "name": "r/gamedeals",
            "url": "https://www.reddit.com/r/gamedeals/.rss",
            "type": "reddit",
        },
    ],
    "monitors": [
        {
            "name": "GPU Deals",
            "terms": ["RTX 4070", "RX 7800 XT", "RX 7900"],
            "max_price": 400.0,
            "feeds": ["r/deals", "r/buildapcsales"],
            "enabled": True,
        },
        {
            "name": "Example Game Deal",
            "terms": ["Elden Ring", "Cyberpunk"],
            "max_price": 20.0,
            "feeds": ["r/gamedeals"],
            "enabled": False,
        },
    ],
    "notifications": {
        "desktop": True,
        "console": True,
        "notify_historical": False,
    },
    "user_agent": "RedditDealWatcher/1.0 (personal use)",
}


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
