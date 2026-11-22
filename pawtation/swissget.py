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
import http.client
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


def _read(r, n: int) -> bytes:
    """One network read; a timeout, reset, TLS error or cut-off reply becomes a SwissError (local disk errors don't
    pass through here, so they are never blamed on the network)."""
    try:
        return r.read(n)
    except (OSError, http.client.HTTPException) as e:
        raise SwissError(f"The connection to GitHub was interrupted ({e or type(e).__name__}). Try again, or "
                         f"download the release yourself from {RELEASES_PAGE} and choose the file.") from e


def latest_release(timeout: float = 20, opener=None) -> dict:
    """{"tag", "page", "asset": {"name", "size", "url", "sha256" or None}} for the newest official release."""
    with _open(RELEASES_API, timeout, opener) as r:
        try:
            info = json.loads(_read(r, 4 * 1024**2).decode("utf-8"))
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
                chunk = _read(r, CHUNK)
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


_RELEASE_NO = re.compile(r"swiss_r(\d+)", re.IGNORECASE)


def _release_roots(folder: Path, depth: int = 2) -> list[Path]:
    """Folders (folder itself, or up to `depth` levels below it) that hold ActionReplay/AUTOEXEC.DOL, the way an
    unpacked release does. Shallow on purpose: a release is swiss_r<N>/ActionReplay/..., and 7-Zip's "Extract to
    swiss_r<N>\\" adds one level; walking a whole Downloads folder would be slow and could pick a stray copy."""
    found, level = [], [folder]
    for _ in range(depth + 1):
        nxt = []
        for d in level:
            try:
                kids = [k for k in d.iterdir() if k.is_dir()]
            except OSError:
                continue
            for k in kids:
                try:
                    if k.name.lower() == "actionreplay" and any(f.name.lower() == "autoexec.dol" and f.is_file()
                                                               for f in k.iterdir()):
                        found.append(d)
                except OSError:
                    pass
            nxt += [k for k in kids if k.name.lower() != "actionreplay"]
        level = nxt
    return found


def _roles_in(root: Path) -> dict:
    """{role: Path} for an unpacked release folder (ActionReplay/AUTOEXEC.DOL, ActionReplay/SDLOADER.BIN,
    DOL/swiss_r<N>.dol), matching names without caring about case."""
    out = {}
    for sub in ("ActionReplay", "DOL"):
        d = next((k for k in root.iterdir() if k.is_dir() and k.name.lower() == sub.lower()), None)
        if d is None:
            continue
        for f in sorted(d.iterdir()):
            role = _member_role(f"{d.name}/{f.name}") if f.is_file() else None
            if role and role not in out:
                out[role] = f
    return out


def from_local(path: str) -> dict:
    """Use a release the owner downloaded: the .tar.xz, the unpacked folder (from the .7z), or AUTOEXEC.DOL itself.
    Paths are stored absolute. A folder holding several unpacked releases uses the newest (highest r-number)."""
    p = Path(os.path.abspath(os.path.expanduser(str(path))))
    name = p.name.lower()
    if p.is_dir() and (p / AUTOEXEC).is_file() and not (p / "ActionReplay").is_dir():
        files = {AUTOEXEC: str(p / AUTOEXEC)}                  # a folder laid out like Pawtation's own downloads
        files.update({r: str(q) for r, q in companions(p / AUTOEXEC).items()})
        return {"tag": p.name, "source": str(p), "files": files}
    if p.is_dir():
        roots = _release_roots(p)
        if not roots:
            raise SwissError(f"No ActionReplay/AUTOEXEC.DOL in {p} (or the folders just below it). Choose the folder "
                             "you unpacked the Swiss release into (it has an ActionReplay folder).")

        def number(d):
            m = _RELEASE_NO.search(d.name)
            return int(m.group(1)) if m else -1
        root = max(roots, key=lambda d: (number(d), d.name))
        roles = _roles_in(root)
        rec = {"tag": root.name, "source": str(root), "files": {r: str(q) for r, q in roles.items()}}
        if len(roots) > 1:
            rec["note"] = f"{len(roots)} releases in that folder; using the newest, {root.name}"
        return rec
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
        files = {AUTOEXEC: str(p)}
        files.update({r: str(q) for r, q in companions(p).items()})
        return {"tag": p.parent.name, "source": str(p), "files": files}
    raise SwissError("Choose the Swiss release .tar.xz, the folder you unpacked it into, or its "
                     "ActionReplay/AUTOEXEC.DOL.")


def cached(out_dir: Path | None = None) -> dict | None:
    """The release record in out_dir, or the newest downloaded one, if its AUTOEXEC.DOL is still there. File paths
    are rebuilt from the record's own folder, so a Pawtation folder that was moved keeps working."""
    dirs = [Path(out_dir)] if out_dir else sorted((d for d in swiss_dir().glob("*") if d.is_dir()),
                                                  key=lambda d: d.stat().st_mtime, reverse=True) if swiss_dir().is_dir() else []
    for d in dirs:
        rec = core.load_json(d / "release.json", None)
        if isinstance(rec, dict) and (d / AUTOEXEC).is_file():
            return {**rec, "files": {r: str(d / r) for r in (AUTOEXEC, SDLOADER, MAIN_DOL) if (d / r).is_file()}}
    return None


def companions(autoexec: Path) -> dict:
    """The backup-route files that belong with an AUTOEXEC.DOL: SDLOADER.BIN and the main DOL (as swiss.dol).
    Pawtation's own downloads keep them in the same folder; an unpacked release has ActionReplay/SDLOADER.BIN and
    DOL/swiss_r<N>.dol."""
    a = Path(autoexec)
    if (a.parent / SDLOADER).is_file() and (a.parent / MAIN_DOL).is_file():
        return {SDLOADER: a.parent / SDLOADER, MAIN_DOL: a.parent / MAIN_DOL}
    if a.parent.name.lower() == "actionreplay":
        return {r: q for r, q in _roles_in(a.parent.parent).items() if r != AUTOEXEC}
    return {}


def boot_file(cfg: dict) -> str | None:
    """The AUTOEXEC.DOL to put on the boot card: the one chosen in config.json if it is still there, otherwise the
    newest release Pawtation downloaded (e.g. after the Pawtation folder was moved)."""
    boot = cfg.get("boot_card") if isinstance(cfg.get("boot_card"), dict) else {}
    dol = boot.get("swiss_dol")
    if dol and Path(str(dol)).is_file():
        return str(dol)
    rec = cached()
    return rec["files"][AUTOEXEC] if rec else None
