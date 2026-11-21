"""Get the official Swiss release for the boot card, with one click (or from a file you already downloaded).

What this does and does not do:
- Asks GitHub for the newest official release of Swiss (github.com/emukidid/swiss-gc/releases), downloads its
  .tar.xz archive, checks it (size, and the SHA-256 GitHub publishes when it does), and copies out only the boot
  files: ActionReplay/AUTOEXEC.DOL, ActionReplay/SDLOADER.BIN and the main DOL/swiss_r<N>.dol (as swiss.dol).
- Swiss stays exactly as released: nothing is modified, built or sent anywhere (docs/SWISS.md). This is the only
  part of Pawtation that goes online, and only when you ask it to.
- Release layout facts come from docs/RESEARCH_NOTES.md A3.

Files land in <your Pawtation folder>/swiss/<release tag>/ with a release.json describing where they came from.
Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import lzma
import os
import re
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import core

RELEASES_API = "https://api.github.com/repos/emukidid/swiss-gc/releases/latest"
RELEASES_PAGE = "https://github.com/emukidid/swiss-gc/releases"
USER_AGENT = "Pawtation (personal GameCube SD-card helper)"
MAX_ARCHIVE = 512 * 1024**2          # a Swiss release is tens of MB; refuse anything absurd
MAX_MEMBER = 32 * 1024**2            # a boot file is a few MB at most
CHUNK = 256 * 1024

AUTOEXEC = "AUTOEXEC.DOL"            # what the Action Replay starts (copied to the boot card as autoexec.dol)
SDLOADER = "SDLOADER.BIN"            # backup route, needs swiss.dol next to it (docs/GAMECUBE_GUIDE.md)
MAIN_DOL = "swiss.dol"


class SwissError(Exception):
    """Something the owner can act on; the message is shown as is."""


def swiss_dir() -> Path:
    """<your Pawtation folder>/swiss (follows PAWTATION_HOME, like config.json). Git-ignored."""
    return core.HOME / "swiss"


def _safe_tag(tag: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(tag)).strip("._") or "release"


def _open(url: str, timeout: float, opener=None):
    opener = opener or urllib.request.urlopen                  # looked up at call time (tests and proxies can swap it)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.environ.get("PAWTATION_GITHUB_TOKEN")           # build machines only (shared IPs hit GitHub's limit);
    if token and url == RELEASES_API:                          # sent to the API alone, never to the download host
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        return opener(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise SwissError("GitHub is limiting requests right now. Try again in an hour, or download the release "
                             f"yourself from {RELEASES_PAGE} and choose the file.") from e
        raise SwissError(f"GitHub answered {e.code} for {url}. Try again later, or download the release yourself "
                         f"from {RELEASES_PAGE}.") from e
    except (urllib.error.URLError, OSError) as e:
        raise SwissError(f"Could not reach GitHub ({getattr(e, 'reason', e)}). Is this computer online? You can also "
                         f"download the release yourself from {RELEASES_PAGE} and choose the file.") from e


def latest_release(timeout: float = 20, opener=None) -> dict:
    """{"tag", "page", "asset": {"name", "size", "url", "sha256" or None}} for the newest official release."""
    with _open(RELEASES_API, timeout, opener) as r:
        try:
            info = json.loads(r.read(4 * 1024**2).decode("utf-8"))
        except ValueError as e:
            raise SwissError("GitHub sent something that is not release information. Try again later.") from e
    if not isinstance(info, dict) or not info.get("tag_name"):
        raise SwissError("GitHub did not list a Swiss release. Try again later, or download it yourself from "
                         f"{RELEASES_PAGE}.")
    for a in info.get("assets") or []:
        name = str(a.get("name", ""))
        if name.lower().startswith("swiss_") and name.lower().endswith(".tar.xz"):
            digest = str(a.get("digest") or "")
            url = str(a.get("browser_download_url", ""))
            if not url.startswith("https://github.com/"):
                continue                                         # only ever download from GitHub itself
            return {"tag": str(info["tag_name"]), "page": str(info.get("html_url") or RELEASES_PAGE),
                    "asset": {"name": name, "size": int(a.get("size") or 0), "url": url,
                              "sha256": digest[7:].lower() if digest.lower().startswith("sha256:") else None}}
    raise SwissError(f"The newest Swiss release ({info['tag_name']}) has no .tar.xz download. Download the .7z from "
                     f"{RELEASES_PAGE}, unpack it with 7-Zip and choose the unpacked folder.")


def download(release: dict, dest_dir: Path, progress=None, cancel=None, timeout: float = 60,
             opener=None) -> Path | None:
    """Download the release archive into dest_dir. Returns its path, or None if cancelled (nothing left behind).
    progress(done_bytes, total_bytes) is called as it goes."""
    asset = release["asset"]
    if asset["size"] and asset["size"] > MAX_ARCHIVE:
        raise SwissError(f"The release archive is unexpectedly large ({asset['size']} bytes); not downloading it.")
    dest_dir = Path(dest_dir); dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / Path(asset["name"]).name
    part = target.with_name(target.name + ".part")
    sha, done = hashlib.sha256(), 0
    try:
        with _open(asset["url"], timeout, opener) as r, open(part, "wb") as f:
            while True:
                if cancel and cancel():
                    raise _Cancelled()
                chunk = r.read(CHUNK)
                if not chunk:
                    break
                done += len(chunk)
                if done > MAX_ARCHIVE:
                    raise SwissError("The download is larger than any Swiss release should be; stopped.")
                f.write(chunk); sha.update(chunk)
                if progress:
                    progress(done, asset["size"] or 0)
        if asset["size"] and done != asset["size"]:
            raise SwissError(f"The download was cut short ({done} of {asset['size']} bytes). Try again.")
        if asset["sha256"] and sha.hexdigest() != asset["sha256"]:
            raise SwissError("The download does not match the checksum GitHub lists for it. Try again; if it keeps "
                             "happening, download it yourself from " + RELEASES_PAGE)
        os.replace(part, target)
        return target
    except _Cancelled:
        return None
    finally:
        if part.exists():
            try: part.unlink()
            except OSError: pass


class _Cancelled(Exception):
    pass


def _member_role(name: str) -> str | None:
    """Which boot file a path inside the archive is, judged by its last two path parts (case-insensitive)."""
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if len(parts) < 2 or ".." in parts:
        return None
    folder, file = parts[-2].lower(), parts[-1].lower()
    if folder == "actionreplay" and file == "autoexec.dol":
        return AUTOEXEC
    if folder == "actionreplay" and file == "sdloader.bin":
        return SDLOADER
    if folder == "dol" and re.fullmatch(r"swiss_r\d+\.dol", file):
        return MAIN_DOL
    return None


def extract_boot_files(archive: Path, out_dir: Path) -> dict:
    """Copy only the boot files out of a release .tar.xz (never extracting anything else, never following paths
    from the archive). Returns {role: Path}. Raises SwissError if AUTOEXEC.DOL is not in it."""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    found: dict = {}
    try:
        with tarfile.open(archive, mode="r:xz") as tar:
            for m in tar:
                role = _member_role(m.name)
                if not role or role in found or not m.isfile():
                    continue
                if m.size > MAX_MEMBER:
                    raise SwissError(f"{m.name} in the archive is unexpectedly large; not using it.")
                src = tar.extractfile(m)
                if src is None:
                    continue
                data = src.read(MAX_MEMBER + 1)
                core._write_atomic(out_dir / role, [data])
                found[role] = out_dir / role
    except (tarfile.TarError, lzma.LZMAError, EOFError, OSError, ValueError) as e:
        raise SwissError(f"Could not read {Path(archive).name} ({e}). Download it again.") from e
    if AUTOEXEC not in found:
        raise SwissError(f"{Path(archive).name} has no ActionReplay/AUTOEXEC.DOL in it, so it is not a Swiss release "
                         "Pawtation can use for an Action Replay boot card.")
    return found


def _record(out_dir: Path, info: dict) -> dict:
    files = {role: str(out_dir / role) for role in (AUTOEXEC, SDLOADER, MAIN_DOL) if (out_dir / role).is_file()}
    rec = {**info, "files": files, "saved": int(time.time())}
    core.save_json(out_dir / "release.json", rec)
    return rec


def get_latest(progress=None, cancel=None, opener=None) -> dict | None:
    """Download (or reuse) the newest official release's boot files. Returns the release record
    {"tag", "source", "files": {role: path}, ...}, or None if cancelled."""
    rel = latest_release(opener=opener)
    out_dir = swiss_dir() / _safe_tag(rel["tag"])
    have = cached(out_dir)
    if have:
        return have
    archive = download(rel, out_dir, progress=progress, cancel=cancel, opener=opener)
    if archive is None:
        return None
    try:
        extract_boot_files(archive, out_dir)
    finally:
        try: archive.unlink()                               # only the boot files are kept
        except OSError: pass
    return _record(out_dir, {"tag": rel["tag"], "source": rel["asset"]["url"], "page": rel["page"],
                             "sha256": rel["asset"]["sha256"]})


def from_local(path: str) -> dict:
    """Use a release the owner downloaded: the .tar.xz, the unpacked folder (from the .7z), or AUTOEXEC.DOL itself."""
    p = Path(path)
    name = p.name.lower()
    if p.is_dir():
        hits = sorted(q for q in p.rglob("*") if q.is_file() and _member_role(q.relative_to(p).as_posix()))
        roles = {}
        for q in hits:
            roles.setdefault(_member_role(q.relative_to(p).as_posix()), q)
        if AUTOEXEC not in roles:
            raise SwissError(f"No ActionReplay/AUTOEXEC.DOL inside {p}. Choose the folder you unpacked the Swiss "
                             "release into (it has an ActionReplay folder).")
        return {"tag": p.name, "source": str(p), "files": {r: str(q) for r, q in roles.items()}}
    if not p.is_file():
        raise SwissError(f"Not found: {p}")
    if name.endswith(".7z"):
        raise SwissError("Pawtation cannot open .7z files. Unpack it with 7-Zip and choose the unpacked folder, or "
                         "use the .tar.xz download from the same release page.")
    if name.endswith(".tar.xz"):
        out_dir = swiss_dir() / ("local-" + _safe_tag(p.name[:-7]))
        extract_boot_files(p, out_dir)
        return _record(out_dir, {"tag": p.name[:-7], "source": str(p)})
    if name == "autoexec.dol":
        return {"tag": p.parent.name, "source": str(p), "files": {AUTOEXEC: str(p)}}
    raise SwissError("Choose the Swiss release .tar.xz, the folder you unpacked it into, or its "
                     "ActionReplay/AUTOEXEC.DOL.")


def cached(out_dir: Path | None = None) -> dict | None:
    """The release record in out_dir, or the newest downloaded one, if its AUTOEXEC.DOL is still there."""
    dirs = [Path(out_dir)] if out_dir else sorted((d for d in swiss_dir().glob("*") if d.is_dir()),
                                                  key=lambda d: d.stat().st_mtime, reverse=True) if swiss_dir().is_dir() else []
    for d in dirs:
        rec = core.load_json(d / "release.json", None)
        if isinstance(rec, dict) and isinstance(rec.get("files"), dict) and Path(str(rec["files"].get(AUTOEXEC, ""))).is_file():
            return rec
    return None
