# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for RedditDealWatcher.

Build with:
    pyinstaller RedditDealWatcher.spec
Output: dist/RedditDealWatcher.exe
"""

from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_all

block_cipher = None

# Collect all platform-specific plyer backends so notifications work.
plyer_hidden = collect_submodules("plyer")

# feedparser uses lazy imports for its date/content parsers.
feedparser_hidden = collect_submodules("feedparser")

# pystray has platform-specific backends.
pystray_hidden = collect_submodules("pystray")

# sv-ttk bundles TCL theme files that must be included as data.
sv_ttk_datas, sv_ttk_binaries, sv_ttk_hidden = collect_all("sv_ttk")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[
        *sv_ttk_binaries,
    ],
    datas=[
        # Bundle the icons folder so get_asset_dir() can find icon.ico at runtime.
        ("icons", "icons"),
        *sv_ttk_datas,
    ],
    hiddenimports=[
        *plyer_hidden,
        *feedparser_hidden,
        *pystray_hidden,
        *sv_ttk_hidden,
        # tkinter is stdlib but PyInstaller occasionally needs a nudge.
        "tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
        "tkinter.simpledialog",
        "tkinter.font",
        # email.utils used by gui/utils.py for RFC 2822 date parsing.
        "email.utils",
        "email.header",
        # schedule, rich, requests are usually auto-detected but list
        # them explicitly to be safe.
        "schedule",
        "rich",
        "rich.logging",
        "rich.table",
        "rich.console",
        "requests",
        "charset_normalizer",  # requests dependency
        # pystray + Pillow for system tray icon.
        "pystray",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "unittest",
        "test",
        "pip",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="RedditDealWatcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Windowed = no console window when double-clicked.
    # CLI subcommands still work when launched from a terminal.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icons/icon.ico",
)
