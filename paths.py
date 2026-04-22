"""Resolve the user-writable data directory for config and database files.

When running as a PyInstaller-frozen exe the working directory may be
read-only (e.g. Program Files), so persistent data is stored in
%APPDATA%\\RSSniper instead.  In a plain Python environment the
current working directory is used, preserving existing behaviour.
"""

import os
import sys
from pathlib import Path


def get_data_dir() -> Path:
    """Return (and create if necessary) the directory for persistent data."""
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        data_dir = base / "RSSniper"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    return Path.cwd()


def get_asset_dir() -> Path:
    """Return the directory containing bundled assets (icons, etc.).

    When frozen by PyInstaller, assets live in sys._MEIPASS.
    When running from source they live next to this file.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent
