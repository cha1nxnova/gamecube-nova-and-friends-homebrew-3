"""Where Pawtation's files live, whether it runs from source or as the packaged Pawtation.exe.

Two places, kept apart so a packaged build never loses your settings:

- BUNDLE: files that ship with the app and are only ever read (data/, assets/). From source that is the repository;
  in the one-file .exe it is the folder PyInstaller unpacks to (sys._MEIPASS), which is deleted when the app closes.
- ROOT: your own files (config.json, state.json, packs/, mods/, plugins/, downloaded Swiss releases). From source that
  is the repository, as before; in the .exe it is the folder holding Pawtation.exe, or, if that folder cannot be
  written to (e.g. Program Files), %LOCALAPPDATA%\\Pawtation.

Standard library only, and no imports from the rest of the package, so every module can use it.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent
FROZEN = bool(getattr(sys, "frozen", False))


def _writable(folder: Path) -> bool:
    """True if a file can really be created there (os.access is unreliable on Windows)."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix=".pawtation-probe-", dir=str(folder))
        os.close(fd)
        os.unlink(probe)
        return True
    except OSError:
        return False


def _bundle() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if FROZEN and meipass else SOURCE


def _root() -> Path:
    if not FROZEN:
        return SOURCE
    beside = Path(sys.executable).resolve().parent
    if _writable(beside):
        return beside
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Pawtation"
    local.mkdir(parents=True, exist_ok=True)
    return local


BUNDLE = _bundle()
ROOT = _root()
