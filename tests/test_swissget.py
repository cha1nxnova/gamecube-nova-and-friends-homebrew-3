"""The one-click Swiss download and the packaged-app paths. A fake GitHub and a fake release archive stand in for
the real ones: nothing here goes online or touches a real config, state or card."""
import argparse, contextlib, hashlib, importlib, io, json, sys, tarfile, unittest, urllib.error
from pathlib import Path
from unittest import mock

from pawtation import cli, core, paths, swissget
from test_features import mktmp


def fake_release(folder: Path, n=9999, extra=()) -> Path:
    """A .tar.xz laid out like a Swiss release (docs/RESEARCH_NOTES.md A3), plus optional hostile members."""
    arc = folder / f"swiss_r{n}.tar.xz"
    with tarfile.open(arc, "w:xz") as tar:
        def add(name, data, kind=tarfile.REGTYPE, link=""):
            ti = tarfile.TarInfo(name); ti.size = len(data) if kind == tarfile.REGTYPE else 0; ti.type = kind
            ti.linkname = link
            tar.addfile(ti, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
        for name, data, kind, link in extra:
            add(name, data, kind, link)
        add(f"swiss_r{n}/ActionReplay/AUTOEXEC.DOL", b"AR-DOL")
        add(f"swiss_r{n}/ActionReplay/SDLOADER.BIN", b"SDLOADER")
        add(f"swiss_r{n}/DOL/swiss_r{n}.dol", b"MAIN-DOL")
        add(f"swiss_r{n}/DOL/Legacy/swiss_r{n}-lz.dol", b"LEGACY")
        add(f"swiss_r{n}/LICENSE.txt", b"GPL")
    return arc


class FakeGitHub:
    """urlopen stand-in: the releases API and one asset download."""
    def __init__(self, archive: Path, digest=True, size=None, api_status=200):
        self.data = archive.read_bytes()
        self.calls = []
        self.api_status = api_status
        sha = hashlib.sha256(self.data).hexdigest()
        self.info = {"tag_name": "v0.6r9999", "html_url": "https://github.com/emukidid/swiss-gc/releases/tag/v0.6r9999",
                     "assets": [{"name": "swiss_r9999.7z", "size": 1, "browser_download_url": "https://github.com/x.7z"},
                                {"name": archive.name, "size": len(self.data) if size is None else size,
                                 "digest": f"sha256:{sha}" if digest is True else digest,
                                 "browser_download_url": "https://github.com/emukidid/swiss-gc/releases/download/v0.6r9999/" + archive.name}]}

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.calls.append(url)
        if url == swissget.RELEASES_API:
            if self.api_status != 200:
                raise urllib.error.HTTPError(url, self.api_status, "nope", {}, None)
            return io.BytesIO(json.dumps(self.info).encode())
        return io.BytesIO(self.data)


class Download(unittest.TestCase):
    def setUp(self):
        self.tmp = mktmp(self)
        self.home = self.tmp / "home"; self.home.mkdir()
        p = mock.patch.object(core, "HOME", self.home); p.start(); self.addCleanup(p.stop)
        self.gh = FakeGitHub(fake_release(self.tmp))

    def test_downloads_and_keeps_only_the_boot_files(self):
        rec = swissget.get_latest(opener=self.gh)
        out = self.home / "swiss" / "v0.6r9999"
        self.assertEqual(Path(rec["files"]["AUTOEXEC.DOL"]).read_bytes(), b"AR-DOL")
        self.assertEqual((out / "SDLOADER.BIN").read_bytes(), b"SDLOADER")
        self.assertEqual((out / "swiss.dol").read_bytes(), b"MAIN-DOL")
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["AUTOEXEC.DOL", "SDLOADER.BIN", "release.json", "swiss.dol"])
        self.assertEqual(swissget.cached()["tag"], "v0.6r9999")

    def test_a_second_run_reuses_the_download(self):
        swissget.get_latest(opener=self.gh)
        n = len(self.gh.calls)
        swissget.get_latest(opener=self.gh)
        self.assertEqual(len(self.gh.calls), n + 1)                       # only the release check, no download

    def test_checksum_and_size_mismatches_are_refused(self):
        bad = FakeGitHub(fake_release(self.tmp), digest="sha256:" + "0" * 64)
        with self.assertRaises(swissget.SwissError):
            swissget.get_latest(opener=bad)
        short = FakeGitHub(fake_release(self.tmp), size=10**6)
        with self.assertRaises(swissget.SwissError):
            swissget.get_latest(opener=short)
        self.assertIsNone(swissget.cached())
        self.assertEqual([p for p in (self.home / "swiss").rglob("*") if p.is_file()], [])

    def test_rate_limit_gives_a_plain_message(self):
        with self.assertRaises(swissget.SwissError) as e:
            swissget.get_latest(opener=FakeGitHub(fake_release(self.tmp), api_status=403))
        self.assertIn("download the release", str(e.exception))

    def test_cancel_leaves_nothing_behind(self):
        self.assertIsNone(swissget.get_latest(opener=self.gh, cancel=lambda: True))
        self.assertEqual([p for p in (self.home / "swiss").rglob("*") if p.is_file()], [])

    def test_hostile_archive_members_are_never_written(self):
        arc = fake_release(self.tmp, n=1, extra=[
            ("../../evil/ActionReplay/AUTOEXEC.DOL", b"EVIL", tarfile.REGTYPE, ""),
            ("/abs/ActionReplay/SDLOADER.BIN", b"EVIL", tarfile.REGTYPE, ""),
            ("x/DOL/swiss_r1.dol", b"", tarfile.SYMTYPE, "/etc/passwd")])
        out = self.tmp / "out"
        found = swissget.extract_boot_files(arc, out)
        self.assertEqual((out / "AUTOEXEC.DOL").read_bytes(), b"AR-DOL")      # the real one, not the '..' one
        self.assertFalse((self.tmp / "evil").exists())
        self.assertEqual(set(found), {"AUTOEXEC.DOL", "SDLOADER.BIN", "swiss.dol"})

    def test_an_archive_without_the_action_replay_file_is_refused(self):
        arc = self.tmp / "other.tar.xz"
        with tarfile.open(arc, "w:xz") as tar:
            ti = tarfile.TarInfo("readme.txt"); ti.size = 2; tar.addfile(ti, io.BytesIO(b"hi"))
        with self.assertRaises(swissget.SwissError):
            swissget.extract_boot_files(arc, self.tmp / "o")
        (self.tmp / "junk.tar.xz").write_bytes(b"not an archive")
        with self.assertRaises(swissget.SwissError):
            swissget.extract_boot_files(self.tmp / "junk.tar.xz", self.tmp / "o2")


class LocalFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = mktmp(self)
        p = mock.patch.object(core, "HOME", self.tmp / "home"); p.start(); self.addCleanup(p.stop)

    def test_unpacked_folder_archive_and_dol(self):
        rel = self.tmp / "swiss_r9999" / "ActionReplay"; rel.mkdir(parents=True)
        (rel / "AUTOEXEC.DOL").write_bytes(b"AR")
        self.assertEqual(swissget.from_local(str(self.tmp / "swiss_r9999"))["files"]["AUTOEXEC.DOL"], str(rel / "AUTOEXEC.DOL"))
        self.assertEqual(swissget.from_local(str(rel / "AUTOEXEC.DOL"))["files"]["AUTOEXEC.DOL"], str(rel / "AUTOEXEC.DOL"))
        rec = swissget.from_local(str(fake_release(self.tmp)))
        self.assertEqual(Path(rec["files"]["AUTOEXEC.DOL"]).read_bytes(), b"AR-DOL")

    def test_7z_and_wrong_files_explain_what_to_do(self):
        (self.tmp / "swiss_r1.7z").write_bytes(b"7z")
        with self.assertRaises(swissget.SwissError) as e:
            swissget.from_local(str(self.tmp / "swiss_r1.7z"))
        self.assertIn("7-Zip", str(e.exception))
        (self.tmp / "empty").mkdir()
        with self.assertRaises(swissget.SwissError):
            swissget.from_local(str(self.tmp / "empty"))


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = mktmp(self)
        for name, value in (("HOME", self.tmp), ("CONFIG_PATH", self.tmp / "config.json"),
                            ("STATE_PATH", self.tmp / "state.json")):
            p = mock.patch.object(core, name, value); p.start(); self.addCleanup(p.stop)

    def test_swiss_get_then_boot_card_uses_the_download(self):
        gh = FakeGitHub(fake_release(self.tmp))
        out = io.StringIO()
        with mock.patch.object(swissget.urllib.request, "urlopen", gh), contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_swiss(argparse.Namespace(action="get", path=None)), 0)
        dol = core.load_config()["boot_card"]["swiss_dol"]
        self.assertTrue(dol.endswith("AUTOEXEC.DOL"))
        card = self.tmp / "card"; card.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(cli.cmd_boot_card(argparse.Namespace(mount=str(card), swiss_dol=None, go=True, force=False)))
        self.assertEqual((card / "autoexec.dol").read_bytes(), b"AR-DOL")


class BootCardFormat(unittest.TestCase):
    def test_a_card_that_is_not_fat_is_named(self):
        tmp = mktmp(self); dol = tmp / "AUTOEXEC.DOL"; dol.write_bytes(b"x")
        with mock.patch.object(core, "volume_info", lambda p: {"fs": "NTFS"}):
            warns = core.prepare_boot_card(str(tmp), str(dol), log=lambda *_: None)["warnings"]
        self.assertTrue(any("NTFS" in w for w in warns))
        with mock.patch.object(core, "volume_info", lambda p: {"fs": "FAT"}):
            warns = core.prepare_boot_card(str(tmp), str(dol), log=lambda *_: None)["warnings"]
        self.assertFalse(any("formatted as" in w for w in warns))


class PackagedPaths(unittest.TestCase):
    """In Pawtation.exe the shipped files and your own files live in different places."""
    def reload_with(self, **attrs):
        with mock.patch.multiple(sys, create=True, **attrs):
            return importlib.reload(paths)

    def tearDown(self):
        importlib.reload(paths)                                           # back to the source layout

    def test_frozen_layout(self):
        tmp = mktmp(self)
        app = tmp / "Pawtation"; app.mkdir(); unpacked = tmp / "_MEI123"; unpacked.mkdir()
        p = self.reload_with(frozen=True, _MEIPASS=str(unpacked), executable=str(app / "Pawtation.exe"))
        self.assertEqual(p.BUNDLE, unpacked)
        self.assertEqual(p.ROOT, app.resolve())

    def test_unwritable_exe_folder_falls_back_to_local_app_data(self):
        tmp = mktmp(self)
        with mock.patch.dict("os.environ", {"LOCALAPPDATA": str(tmp / "local")}), \
                mock.patch("tempfile.mkstemp", side_effect=OSError("read-only")):
            p = self.reload_with(frozen=True, _MEIPASS=str(tmp), executable=str(tmp / "ro" / "Pawtation.exe"))
            self.assertEqual(p.ROOT, tmp / "local" / "Pawtation")

    def test_source_layout_is_unchanged(self):
        self.assertEqual(paths.ROOT, Path(core.__file__).resolve().parent.parent)
        self.assertEqual(core.DATA_DIR, paths.BUNDLE / "data")


if __name__ == "__main__":
    unittest.main()
