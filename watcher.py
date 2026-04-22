import re
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable

import feedparser
import requests

from database import (
    is_seen,
    mark_seen,
    get_last_checked,
    set_last_checked,
    is_deal_matched,
    mark_deal_matched,
    get_seen_items_since,
    sync_deal_matches_published,
    delete_deal_match,
    get_seen_items_for_feed,
)

log = logging.getLogger("watcher")

_PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")

MAX_LOOKBACK_DAYS = 3  # default; overridden by config at runtime
_MAX_ENTRIES_PER_FEED = 1000  # default; overridden by config at runtime

# Named regex presets for match_pattern.  Each pattern's first capture group
# is used as the text to match monitor terms against.  Exposed here so the GUI
# can offer them as quick-fill options without duplicating the strings.
PRESET_PATTERNS: dict[str, str] = {
    "[H]/[W] boards (r/hardwareswap, r/mechmarket)": r"\[H\](.+?)(?=\[W\]|$)",
    "Title only — ignore post body": r"^(.+)$",
}


def extract_match_text(entry: dict, feed_cfg: dict) -> str:
    """Return the text to match monitor terms against for *entry*.

    If the feed has a ``match_pattern`` field, the regex is applied to the
    post title.  The first capture group (or the full match if no groups) is
    returned.  If the pattern is present but does NOT match the title, an
    empty string is returned so the entry is excluded from matching — the
    pattern acts as a filter, not just an extractor.

    Falls back to ``title + summary`` only when no pattern is configured, or
    when the pattern is invalid (regex error).
    """
    pattern = feed_cfg.get("match_pattern", "").strip()
    if pattern:
        try:
            m = re.search(pattern, entry["title"], re.IGNORECASE)
            if m:
                return m.group(1) if m.lastindex else m.group(0)
            # Pattern set but title didn't match → exclude this entry.
            return ""
        except re.error:
            log.warning(
                f"[{feed_cfg.get('name', '?')}] invalid match_pattern "
                f"{pattern!r} — falling back to full text"
            )
    return f"{entry['title']} {entry['summary']}"


def strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub(" ", text)


def extract_prices(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in _PRICE_RE.findall(text)]


def _parse_published(entry) -> Optional[datetime]:
    """Convert feedparser's published_parsed (struct_time) to a UTC-aware datetime."""
    t = getattr(entry, "published_parsed", None)
    if t:
        try:
            return datetime(*t[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
    return None


def _reddit_fullname(link: str) -> Optional[str]:
    """Extract the Reddit post fullname (t3_POSTID) from a post link for use as *after*."""
    m = re.search(r"/comments/([a-z0-9]+)/", link)
    return f"t3_{m.group(1)}" if m else None


def _contextual_prices(text: str, term: str) -> list[float]:
    """Return prices found on the same line as *term* (case-insensitive).

    Splits *text* into lines, finds lines containing *term*, and extracts
    dollar amounts from those lines only.  Returns an empty list if none found.
    """
    term_lower = term.lower()
    prices: list[float] = []
    for line in text.splitlines():
        if term_lower in line.lower():
            prices.extend(extract_prices(line))
    return prices


def matches_monitor(
    entry_text: str, monitor: dict
) -> tuple[bool, Optional[float]]:
    """Return (matched, price). Term matching is OR — any one term triggers.

    Price is taken from the same line as the matched term when possible,
    falling back to the global minimum across the full text.  This avoids
    mis-attributing prices from unrelated items in multi-item posts.
    """
    text_lower = entry_text.lower()

    terms: list[str] = monitor.get("terms", [])
    matched_term: Optional[str] = None
    if terms:
        for t in terms:
            if t.lower() in text_lower:
                matched_term = t
                break
        if matched_term is None:
            return False, None

    max_price: Optional[float] = monitor.get("max_price")

    # Prefer prices on the same line as the matched keyword; fall back to global.
    if matched_term:
        prices = _contextual_prices(entry_text, matched_term)
    else:
        prices = []
    if not prices:
        prices = extract_prices(entry_text)

    if max_price is not None:
        if not prices:
            return True, None  # terms matched, price unknown
        lowest = min(prices)
        if lowest <= max_price:
            return True, lowest
        return False, None

    return True, (min(prices) if prices else None)


def fetch_feed(
    feed_cfg: dict,
    user_agent: str,
    cutoff: Optional[datetime] = None,
    max_entries: int = _MAX_ENTRIES_PER_FEED,
    page_delay: float = 0.75,
    timeout: int = 15,
) -> list[dict]:
    """Fetch an RSS/Atom feed, paginating back to *cutoff*.

    Pagination is attempted automatically using Reddit's ``?after=t3_POSTID``
    cursor.  For non-Reddit feeds ``_reddit_fullname`` returns ``None`` and the
    loop stops after the first page, so the behaviour is identical to before.
    A seen-IDs guard prevents infinite loops if a feed returns the same page
    twice.

    *cutoff* defaults to ``MAX_LOOKBACK_DAYS`` ago (UTC).
    """
    if cutoff is None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_LOOKBACK_DAYS)

    headers = {"User-Agent": user_agent}
    base_url = feed_cfg["url"]

    all_entries: list[dict] = []
    seen_ids: set[str] = set()
    after: Optional[str] = None
    first_page = True

    while True:
        params: dict = {"limit": 100}
        if after:
            params["after"] = after

        if not first_page:
            time.sleep(page_delay)  # polite delay between paginated requests
        first_page = False

        try:
            resp = requests.get(
                base_url, headers=headers, params=params, timeout=timeout
            )
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
        except requests.RequestException as exc:
            log.warning(f"Could not fetch {feed_cfg['name']}: {exc}")
            break

        if not parsed.entries:
            break

        oldest_in_page: Optional[datetime] = None
        new_on_page = 0
        for e in parsed.entries:
            entry_id = getattr(e, "id", None) or e.get("link", "")
            if entry_id in seen_ids:
                continue  # duplicate page — stop pagination
            seen_ids.add(entry_id)
            new_on_page += 1

            pub = _parse_published(e)
            raw_summary = getattr(e, "summary", "") or ""
            all_entries.append(
                {
                    "id": entry_id,
                    "title": getattr(e, "title", ""),
                    "link": getattr(e, "link", ""),
                    "summary": strip_html(raw_summary),
                    "summary_html": raw_summary,
                    "published": getattr(e, "published", ""),
                    "_pub_dt": pub,
                }
            )
            if pub and (oldest_in_page is None or pub < oldest_in_page):
                oldest_in_page = pub

        if new_on_page == 0:
            break  # all entries on this page were duplicates

        # Stop once the oldest entry on this page predates the cutoff
        if oldest_in_page is not None and oldest_in_page < cutoff:
            break

        if len(all_entries) >= max_entries:
            break

        # Attempt to get the next-page cursor (Reddit-style).
        # For non-Reddit feeds this returns None and pagination stops.
        last_link = getattr(parsed.entries[-1], "link", "")
        after = _reddit_fullname(last_link)
        if not after:
            break

    # Drop the internal datetime field and filter entries older than cutoff
    result: list[dict] = []
    for entry in all_entries:
        pub = entry.pop("_pub_dt", None)
        if pub is None or pub >= cutoff:
            result.append(entry)

    return result


def check_feeds(
    config: dict,
    conn,
    on_match: Optional[Callable] = None,
) -> None:
    feeds_by_name = {f["name"]: f for f in config["feeds"]}
    user_agent: str = config.get("user_agent", "RSSniper/1.0")
    now_utc = datetime.now(timezone.utc)
    lookback_days: int = int(
        config.get("max_lookback_days", MAX_LOOKBACK_DAYS)
    )
    max_entries: int = int(
        config.get("max_entries_per_feed", _MAX_ENTRIES_PER_FEED)
    )
    page_delay: float = float(config.get("page_delay_seconds", 0.75))
    timeout: int = int(config.get("request_timeout_seconds", 15))
    max_lookback = now_utc - timedelta(days=lookback_days)

    # Collect all feed names referenced by enabled monitors (deduplicated so
    # each feed is fetched only once even if multiple monitors share it).
    active_feed_names: set[str] = set()
    for monitor in config["monitors"]:
        if not monitor.get("enabled", True):
            continue
        for name in monitor.get("feeds", list(feeds_by_name.keys())):
            active_feed_names.add(name)

    # Fetch each active feed once, paging back to max(last_checked, max_lookback).
    feed_entries: dict[str, list[dict]] = {}
    for feed_name in active_feed_names:
        feed_cfg = feeds_by_name.get(feed_name)
        if feed_cfg is None:
            log.warning(f"Unknown feed '{feed_name}' referenced by a monitor")
            continue

        last_checked = get_last_checked(conn, feed_name)
        if last_checked is None:
            cutoff = max_lookback
        else:
            # Cap at max_lookback so we never retrieve more than MAX_LOOKBACK_DAYS
            cutoff = max(last_checked, max_lookback)

        log.info(
            f"[{feed_name}] fetching entries since "
            f"{cutoff.strftime('%Y-%m-%d %H:%M')} UTC …"
        )
        entries = fetch_feed(
            feed_cfg,
            user_agent,
            cutoff=cutoff,
            max_entries=max_entries,
            page_delay=page_delay,
            timeout=timeout,
        )
        feed_entries[feed_name] = entries
        log.info(f"[{feed_name}] {len(entries)} entries retrieved")

    # Run monitor matching across all fetched entries.
    for monitor in config["monitors"]:
        if not monitor.get("enabled", True):
            continue

        target_feed_names: list[str] = monitor.get(
            "feeds", list(feeds_by_name.keys())
        )

        for feed_name in target_feed_names:
            for entry in feed_entries.get(feed_name, []):
                item_id: str = entry["id"] or entry["link"]
                if not item_id or is_seen(conn, item_id):
                    continue

                full_text = extract_match_text(
                    entry, feeds_by_name.get(feed_name, {})
                )
                matched, price = matches_monitor(full_text, monitor)

                if matched:
                    log.info(
                        f"  MATCH [{monitor['name']}] {entry['title'][:80]}"
                    )
                    mark_deal_matched(
                        conn,
                        item_id,
                        monitor["name"],
                        price=price,
                        published=entry.get("published", ""),
                    )
                    if on_match:
                        on_match(
                            monitor=monitor,
                            feed_name=feed_name,
                            entry=entry,
                            price=price,
                        )

    # Mark every fetched entry as seen and record the last-checked timestamp.
    for feed_name, entries in feed_entries.items():
        for entry in entries:
            item_id = entry["id"] or entry["link"]
            if item_id:
                mark_seen(
                    conn,
                    item_id,
                    feed_name,
                    entry["title"],
                    entry["link"],
                    published=entry.get("published", ""),
                )
        set_last_checked(conn, feed_name)


def scan_seen_for_deals(
    config: dict,
    conn,
    on_match: Optional[Callable] = None,
    notify_historical: bool = False,
) -> None:
    """Scan already-seen DB items against active monitors.

    Fires *on_match* (with ``notify=False``) for any (item, monitor) pair
    that hasn't been reported yet.  Only looks back MAX_LOOKBACK_DAYS.
    Title-only matching is used because full post bodies aren't stored in the DB.
    """
    now_utc = datetime.now(timezone.utc)
    lookback_days: int = int(
        config.get("max_lookback_days", MAX_LOOKBACK_DAYS)
    )
    since = now_utc - timedelta(days=lookback_days)
    items = get_seen_items_since(conn, since)
    if not items:
        return

    log.info(f"Scanning {len(items)} stored items against monitors …")
    feeds_by_name = {f["name"]: f for f in config["feeds"]}
    matches_found = 0

    for monitor in config["monitors"]:
        if not monitor.get("enabled", True):
            continue
        target_feeds: set[str] = set(
            monitor.get("feeds", list(feeds_by_name.keys()))
        )

        for item in items:
            if item["feed"] not in target_feeds:
                continue
            item_id = item["id"]
            if not item_id or is_deal_matched(conn, item_id, monitor["name"]):
                continue

            feed_cfg = feeds_by_name.get(item["feed"], {})
            match_text = extract_match_text(
                {"title": item["title"], "summary": ""}, feed_cfg
            )
            matched, price = matches_monitor(match_text, monitor)
            if matched:
                log.info(
                    f"  DB-MATCH [{monitor['name']}] {item['title'][:80]}"
                )
                mark_deal_matched(
                    conn,
                    item_id,
                    monitor["name"],
                    price=price,
                    published=item.get("published", ""),
                )
                matches_found += 1
                if on_match:
                    entry = {
                        "id": item_id,
                        "title": item["title"],
                        "link": item["url"],
                        "summary": "",
                        "summary_html": "",
                        "published": item.get("published", ""),
                    }
                    on_match(
                        monitor=monitor,
                        feed_name=item["feed"],
                        entry=entry,
                        price=price,
                        notify=notify_historical,
                    )

    if matches_found:
        log.info(
            f"DB scan complete — {matches_found} historical match(es) found."
        )
    else:
        log.info("DB scan complete — no new historical matches.")


def reeval_feed_pattern(config: dict, conn, feed_name: str) -> tuple[int, int]:
    """Re-evaluate all stored seen_items for *feed_name* against active monitors.

    Uses the feed's current ``match_pattern`` from *config*.  Removes
    deal_matches that no longer match under the new pattern and adds any that
    now match for the first time.  Returns ``(removed, added)`` counts.

    Note: only the stored ``title`` field is available for DB items; the post
    body is not stored.  For a pattern that relies on the body the results may
    differ from a live fetch, but title-based re-evaluation is accurate for the
    common structured-title patterns (e.g. [H]/[W] boards).
    """
    feeds_by_name = {f["name"]: f for f in config["feeds"]}
    feed_cfg = feeds_by_name.get(feed_name)
    if feed_cfg is None:
        return 0, 0

    items = get_seen_items_for_feed(conn, feed_name)
    if not items:
        return 0, 0

    removed = 0
    added = 0

    for monitor in config["monitors"]:
        if not monitor.get("enabled", True):
            continue
        target_feeds: set[str] = set(
            monitor.get("feeds", list(feeds_by_name.keys()))
        )
        if feed_name not in target_feeds:
            continue

        for item in items:
            item_id = item["id"]
            if not item_id:
                continue

            # Use title only (body not stored in DB); summary set to "" so
            # full-text fallback is title-only, not title + empty string noise.
            entry = {"title": item["title"], "summary": ""}
            match_text = extract_match_text(entry, feed_cfg)
            matched, price = matches_monitor(match_text, monitor)
            was_matched = is_deal_matched(conn, item_id, monitor["name"])

            if was_matched and not matched:
                delete_deal_match(conn, item_id, monitor["name"])
                log.info(f"  REMOVED [{monitor['name']}] {item['title'][:80]}")
                removed += 1
            elif matched and not was_matched:
                mark_deal_matched(
                    conn,
                    item_id,
                    monitor["name"],
                    price=price,
                    published=item.get("published", ""),
                )
                log.info(f"  ADDED   [{monitor['name']}] {item['title'][:80]}")
                added += 1

    if removed or added:
        log.info(
            f"[{feed_name}] pattern re-eval: {removed} removed, {added} added."
        )
    else:
        log.info(f"[{feed_name}] pattern re-eval: no deal changes.")
    return removed, added


def run_check(config: dict, conn, on_match: Optional[Callable] = None) -> None:
    log.info(f"Checking feeds at {datetime.now().strftime('%H:%M:%S')} …")
    check_feeds(config, conn, on_match=on_match)
    notify_hist = config.get("notifications", {}).get(
        "notify_historical", False
    )
    scan_seen_for_deals(
        config, conn, on_match=on_match, notify_historical=notify_hist
    )
    sync_deal_matches_published(conn)
    log.info("Check complete.")
