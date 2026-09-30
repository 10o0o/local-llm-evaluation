import contextlib
import copy
import hashlib
import io
import json
import stat
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from llm_eval import cli, data_setup


class DataSetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "checkout"
        self.root.mkdir()
        (self.root / "data/coci").mkdir(parents=True)
        self.archives = Path(temporary.name) / "archives"
        self.archives.mkdir()
        repo = Path(__file__).resolve().parents[1]
        self.manifest = json.loads((repo / data_setup.MANIFEST_PATH).read_text())
        self.problems = json.loads((repo / "data/coci/problems.json").read_text())
        (self.root / "data/coci/problems.json").write_text(json.dumps(self.problems))
        self.contents = {}
        for archive in self.manifest["archives"]:
            entries = {}
            for name in archive["problem_roots"]:
                entries[f"{name}/"] = b""
                for prefix in (f"{name}", f"{name}.dummy"):
                    entries[f"{name}/{prefix}.in.1"] = b"2 3\n"
                    entries[f"{name}/{prefix}.out.1"] = b"5\n"
            for counts in archive["selected_problems"].values():
                counts.update(cases=1, samples=1)
            self.contents[archive["contest"]] = entries
            self.save_archive(archive["contest"])

    def save_archive(self, contest, extra=None):
        archive = next(a for a in self.manifest["archives"] if a["contest"] == contest)
        path = self.archives / archive["filename"]
        with warnings.catch_warnings(), zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zipped:
            warnings.simplefilter("ignore", UserWarning)
            for name, content in self.contents[contest].items():
                zipped.writestr(name, content)
            if extra:
                zipped.writestr(*extra)
        archive["size_bytes"] = path.stat().st_size
        with path.open("rb") as source:
            archive["sha256"] = hashlib.file_digest(source, "sha256").hexdigest()
        (self.root / data_setup.MANIFEST_PATH).write_text(json.dumps(self.manifest))

    def run_setup(self):
        with contextlib.redirect_stdout(io.StringIO()), \
                patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            return data_setup.setup_dataset(self.root, self.archives)

    def assert_no_install(self):
        for problem in self.problems:
            self.assertFalse((self.root / problem["problem_dir"]).exists())

    def test_cli_contract(self):
        self.assertIsNone(cli.parse_args(["data", "setup"]).archives_dir)
        self.assertEqual(cli.parse_args(["data", "setup", "--archives-dir", "zips"]).archives_dir, Path("zips"))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.parse_args(["data"])

    def test_only_selected_ten_are_installed_and_other_files_preserved(self):
        sentinels = ("results/keep.json", "configs/keep.json", "data/coci/2025_2026/contest5/testdata/other/keep.txt")
        for relative in sentinels:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("keep")
        result = self.run_setup()
        self.assertEqual(len(result), 10)
        for problem in self.problems:
            files = list((self.root / problem["problem_dir"]).iterdir())
            self.assertEqual(len(files), 4)
            self.assertEqual((self.root / problem["problem_dir"] / f"{problem['name']}.in.1").read_bytes(), b"2 3\n")
        self.assertFalse((self.root / "data/coci/2025_2026/contest5/testdata/slaganje").exists())
        for relative in sentinels:
            self.assertEqual((self.root / relative).read_text(), "keep")

    def test_existing_even_empty_destination_rejected_before_download(self):
        target = self.root / self.problems[0]["problem_dir"]
        target.mkdir(parents=True)
        with patch.object(data_setup, "_download") as download, self.assertRaisesRegex(ValueError, "이미 있습니다"):
            data_setup.setup_dataset(self.root)
        download.assert_not_called()
        self.assertEqual(list(target.iterdir()), [])

    def test_symlink_destination_and_ancestor_rejected(self):
        for relative in ("data/coci/2025_2026", self.problems[0]["problem_dir"]):
            with self.subTest(relative=relative):
                target = self.root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(self.root.parent / "absent", target_is_directory=True)
                try:
                    with self.assertRaisesRegex(ValueError, "심볼릭 링크"):
                        self.run_setup()
                finally:
                    target.unlink()

    def test_changed_metadata_cannot_redirect_installation(self):
        self.problems[0]["problem_dir"] = "results/overwrite"
        (self.root / "data/coci/problems.json").write_text(json.dumps(self.problems))
        with self.assertRaisesRegex(ValueError, "문제 경로"):
            self.run_setup()
        self.assertFalse((self.root / "results").exists())

    def test_checksum_mismatch_rejected_before_zip_or_install(self):
        archive = self.manifest["archives"][0]
        path = self.archives / archive["filename"]
        original = path.read_bytes()
        path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        with patch.object(data_setup, "_stage_archive") as stage, self.assertRaisesRegex(ValueError, "SHA-256"):
            self.run_setup()
        stage.assert_not_called()
        self.assert_no_install()

    def test_missing_or_wrong_size_archive_rejected(self):
        (self.archives / self.manifest["archives"][2]["filename"]).write_bytes(b"truncated")
        with self.assertRaisesRegex(ValueError, "크기 불일치"):
            self.run_setup()
        self.assert_no_install()

    def test_unsafe_paths_rejected_even_in_unselected_folder(self):
        for name in ("../escape", "/absolute/file", "C:/escape", "magija/../../escape", "magija\\evil", "magija//file", "magija/./file", "magija/nested/file", "magija/bad\x00name"):
            with self.subTest(name=name):
                # ZipInfo truncates nulls when writing, so test that original
                # header name directly for the embedded-NUL case.
                if "\x00" in name:
                    info = zipfile.ZipInfo(name)
                    with patch.object(zipfile.ZipFile, "infolist", return_value=[info]), \
                            zipfile.ZipFile(self.archives / "contest4_testdata.zip") as zipped, \
                            self.assertRaisesRegex(ValueError, "안전하지 않은"):
                        data_setup._inspect_members(zipped, self.manifest["archives"][0])
                else:
                    self.save_archive(4, (name, b"bad"))
                    with self.assertRaisesRegex(ValueError, "안전하지 않은"):
                        self.run_setup()
                self.assert_no_install()

    def test_duplicate_destination_and_case_collision_rejected(self):
        for name in ("tomahawk/tomahawk.in.1", "tomahawk/TOMAHAWK.in.1"):
            with self.subTest(name=name):
                self.save_archive(4, (name, b"bad"))
                with self.assertRaisesRegex(ValueError, "중복"):
                    self.run_setup()
                self.assert_no_install()

    def test_symlink_and_special_zip_entries_rejected(self):
        for kind in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR):
            with self.subTest(kind=kind):
                info = zipfile.ZipInfo("magija/unsafe")
                info.create_system = 3
                info.external_attr = (kind | 0o777) << 16
                self.save_archive(4, (info, b"target"))
                with self.assertRaisesRegex(ValueError, "링크·특수"):
                    self.run_setup()
                self.assert_no_install()

    def test_encrypted_member_rejected(self):
        archive = self.manifest["archives"][0]
        with zipfile.ZipFile(self.archives / archive["filename"]) as zipped:
            infos = zipped.infolist()
            infos[1].flag_bits |= 1
            with patch.object(zipped, "infolist", return_value=infos), self.assertRaisesRegex(ValueError, "암호화"):
                data_setup._inspect_members(zipped, archive)

    def test_size_ratio_and_count_limits_rejected(self):
        for limit in ("MAX_MEMBERS", "MAX_TOTAL_BYTES", "MAX_MEMBER_BYTES", "MAX_COMPRESSION_RATIO"):
            with self.subTest(limit=limit), patch.object(data_setup, limit, 0.1), self.assertRaisesRegex(ValueError, "제한"):
                self.run_setup()
            self.assert_no_install()

    def test_missing_outputs_and_unpaired_or_wrong_count_inputs_rejected(self):
        original = copy.deepcopy(self.contents[6])
        for action in ("missing_output", "orphan_output", "extra_pair", "unexpected_file"):
            with self.subTest(action=action):
                entries = self.contents[6] = copy.deepcopy(original)
                if action == "missing_output":
                    del entries["cokolada/cokolada.out.1"]
                elif action == "orphan_output":
                    entries["cokolada/cokolada.out.2"] = b"5\n"
                elif action == "extra_pair":
                    entries["cokolada/cokolada.in.2"] = b"2 3\n"
                    entries["cokolada/cokolada.out.2"] = b"5\n"
                else:
                    entries["cokolada/answer.py"] = b"unsafe"
                self.save_archive(6)
                with self.assertRaisesRegex(ValueError, "불일치|예상하지 않은"):
                    self.run_setup()
                self.assert_no_install()

    def test_wrong_season_layout_rejected(self):
        self.save_archive(6, ("different/different.in.1", b"bad"))
        with self.assertRaisesRegex(ValueError, "폴더 구성"):
            self.run_setup()
        self.assert_no_install()

    def test_failed_final_copy_rolls_back_only_new_data(self):
        with patch.object(data_setup.shutil, "copyfileobj", side_effect=OSError("disk full")), self.assertRaisesRegex(OSError, "disk full"):
            self.run_setup()
        self.assert_no_install()

    def test_late_destination_conflict_preserves_existing_data(self):
        install = data_setup._install
        target = self.root / self.problems[0]["problem_dir"]

        def conflicting_install(root, plan, staging):
            target.mkdir(parents=True)
            (target / "keep").write_text("keep")
            return install(root, plan, staging)

        with patch.object(data_setup, "_install", side_effect=conflicting_install), self.assertRaisesRegex(ValueError, "이미 있습니다"):
            self.run_setup()
        self.assertEqual((target / "keep").read_text(), "keep")
        for problem in self.problems[1:]:
            self.assertFalse((self.root / problem["problem_dir"]).exists())

    def test_download_flow_is_mocked_and_goes_through_same_checks(self):
        def fake_download(archive, destination):
            destination.write_bytes((self.archives / archive["filename"]).read_bytes())
        with patch.object(data_setup, "_download", side_effect=fake_download) as download, contextlib.redirect_stdout(io.StringIO()):
            result = data_setup.setup_dataset(self.root)
        self.assertEqual(download.call_count, 3)
        self.assertEqual(len(result), 10)

    def test_download_bound_and_official_redirect_policy(self):
        archive = self.manifest["archives"][0]
        response = io.BytesIO(b"x" * (archive["size_bytes"] + 1))
        with patch.object(data_setup.urllib.request, "build_opener") as opener, contextlib.redirect_stdout(io.StringIO()):
            opener.return_value.open.return_value = response
            with self.assertRaisesRegex(ValueError, "예상 크기"):
                data_setup._download(archive, self.archives / "oversize.zip")
        handler = data_setup.OfficialRedirectsOnly()
        for url in ("http://hsin.hr/coci/data.zip", "https://example.com/data.zip", "https://hsin.hr.evil/coci/data.zip"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "공식 HTTPS"):
                handler.redirect_request(None, None, 302, "redirect", {}, url)
