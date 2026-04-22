import logging

log = logging.getLogger("watcher")


def notify_desktop(title: str, message: str) -> None:
    try:
        from plyer import notification  # type: ignore

        notification.notify(
            title=title,
            message=message[:256],
            app_name="RedditDealWatcher",
            timeout=10,
        )
    except Exception as exc:
        log.debug(f"Desktop notification unavailable: {exc}")
