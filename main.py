#!/usr/bin/env python3
"""
RSSniper — Monitor RSS feeds for deals matching keywords and price thresholds.

Usage:
  python main.py               # Launch GUI (default)
  python main.py gui           # Launch GUI
  python main.py watch         # CLI continuous polling
  python main.py check         # CLI single check then exit
  python main.py list          # CLI list feeds and monitors
  python main.py add-feed NAME URL
  python main.py add-monitor NAME --terms TERM1 TERM2 [--max-price 400] [--feeds FEED1 FEED2]
"""

import logging
import time
from typing import Optional

import schedule
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from config import load_config, save_config
from database import DB_FILE, init_db
from watcher import run_check

console = Console()
log = logging.getLogger("watcher")


# ── CLI helpers ────────────────────────────────────────────────────────────────


def _setup_cli_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(console=console, rich_tracebacks=True, markup=True)
        ],
    )


def cli_list(config: dict) -> None:
    feed_table = Table(
        title="Feeds", show_lines=True, header_style="bold magenta"
    )
    feed_table.add_column("Name", style="cyan")
    feed_table.add_column("URL")
    for f in config["feeds"]:
        feed_table.add_row(f["name"], f["url"])
    console.print(feed_table)

    mon_table = Table(
        title="Monitors", show_lines=True, header_style="bold magenta"
    )
    mon_table.add_column("Name", style="cyan")
    mon_table.add_column("Terms")
    mon_table.add_column("Max Price")
    mon_table.add_column("Feeds")
    mon_table.add_column("Enabled")
    for m in config["monitors"]:
        price_str = (
            f"${m['max_price']:.2f}"
            if m.get("max_price") is not None
            else "any"
        )
        enabled_str = (
            "[green]Yes[/green]" if m.get("enabled", True) else "[red]No[/red]"
        )
        mon_table.add_row(
            m["name"],
            ", ".join(m.get("terms", [])),
            price_str,
            ", ".join(m.get("feeds", ["(all)"])),
            enabled_str,
        )
    console.print(mon_table)


def cli_watch(config: dict, conn) -> None:
    _setup_cli_logging()
    interval: int = config.get("check_interval_minutes", 15)
    log.info(
        f"[bold green]Watcher started[/bold green] — polling every [bold]{interval}[/bold] min.  Ctrl+C to stop."
    )
    run_check(config, conn)
    schedule.every(interval).minutes.do(run_check, config=config, conn=conn)
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        log.info("Watcher stopped.")


def cli_add_feed(config: dict, name: str, url: str) -> None:
    if any(f["name"] == name for f in config["feeds"]):
        console.print(f"[red]Feed '{name}' already exists.[/red]")
        return
    config["feeds"].append({"name": name, "url": url})
    save_config(config)
    console.print(f"[green]Feed '{name}' added.[/green]")


def cli_add_monitor(
    config: dict,
    name: str,
    terms: list[str],
    max_price: Optional[float],
    feeds: list[str],
) -> None:
    monitor: dict = {
        "name": name,
        "terms": terms,
        "enabled": True,
        "feeds": feeds if feeds else [f["name"] for f in config["feeds"]],
    }
    if max_price is not None:
        monitor["max_price"] = max_price
    config["monitors"].append(monitor)
    save_config(config)
    console.print(f"[green]Monitor '{name}' added.[/green]")


# ── Entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="RSSniper — Monitor RSS feeds for deals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Launch GUI (default)
  python main.py gui                # Launch GUI
  python main.py watch              # CLI continuous polling
  python main.py check              # CLI one-shot check
  python main.py list               # CLI list feeds and monitors
  python main.py add-feed "r/mechmarket" https://www.reddit.com/r/mechmarket/.rss
  python main.py add-monitor "Keyboard" --terms "Keychron" "GMMK" --max-price 150 --feeds "r/mechmarket"
        """,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui", help="Launch GUI (default)")
    sub.add_parser("watch", help="CLI continuous polling")
    sub.add_parser("check", help="CLI single check and exit")
    sub.add_parser("list", help="List configured feeds and monitors")

    p_feed = sub.add_parser("add-feed", help="Add a new RSS feed")
    p_feed.add_argument("name", help='Display name, e.g. "r/deals"')
    p_feed.add_argument("url", help="Full RSS URL")

    p_mon = sub.add_parser("add-monitor", help="Add a new monitor rule")
    p_mon.add_argument("name", help="Monitor label")
    p_mon.add_argument("--terms", nargs="+", default=[], metavar="TERM")
    p_mon.add_argument(
        "--max-price", type=float, default=None, metavar="PRICE"
    )
    p_mon.add_argument("--feeds", nargs="+", default=[], metavar="FEED")

    args = parser.parse_args()
    command = args.command or "gui"

    if command == "gui":
        from gui.app import launch_gui

        launch_gui()
        return

    _setup_cli_logging()
    config = load_config()
    conn = init_db(DB_FILE)

    try:
        if command == "list":
            cli_list(config)
        elif command == "check":
            run_check(config, conn)
        elif command == "add-feed":
            cli_add_feed(config, args.name, args.url)
        elif command == "add-monitor":
            cli_add_monitor(
                config, args.name, args.terms, args.max_price, args.feeds
            )
        elif command == "watch":
            cli_watch(config, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
