import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_eval import cli, offline_demo


def mock_judgment(candidate, data, name, limit):
    status = "AC" if candidate.parent.name == "correct" else "WA"
    return {
        "status": status,
        "passed_cases": 3 if status == "AC" else 1,
        "total_cases": 3,
        "max_case_seconds": 0.01,
        "test_results": [],
    }


class OfflineDemoTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "checkout"
        self.root.mkdir()
        self.output = self.root.parent / "demo"

    def test_argument_contract(self):
        args = cli.parse_args(["demo", "offline", "--output", "/tmp/example"])
        self.assertEqual((args.command, args.demo_mode, args.output),
                         ("demo", "offline", Path("/tmp/example")))
        self.assertIsNone(cli.parse_args(["demo", "offline"]).output)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.parse_args(["demo"])

    @patch.object(offline_demo, "judge_problem", side_effect=mock_judgment)
    def test_records_are_explicitly_synthetic_and_reuse_extraction_storage_and_summary(self, judge):
        with contextlib.redirect_stdout(io.StringIO()), \
                patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            result = offline_demo.run_offline_demo(self.root, self.output)
        self.assertEqual(result, self.output)
        self.assertEqual(judge.call_count, 2)
        report = json.loads((result / "report.json").read_text())
        self.assertEqual(report["verdict_counts"], {"AC": 1, "WA": 1, "NO_CODE": 1})
        self.assertTrue(report["synthetic"])
        self.assertFalse(report["is_model_benchmark"])
        self.assertEqual(report["model_calls"], 0)
        self.assertTrue(report["expected_outcomes_matched"])
        self.assertEqual([row["valid_answer"] for row in report["entries"]], [True, False, False])
        for fixture, code, _ in offline_demo.FIXTURES:
            record = json.loads((result / fixture / "result.json").read_text())
            self.assertEqual(record["call"]["status"], "not_called")
            self.assertEqual(record["extracted_code"], code)
            self.assertEqual((result / fixture / "candidate.py").exists(), code is not None)
        self.assertIn(offline_demo.NOTICE, (result / "report.md").read_text())
        self.assertEqual(list(self.root.iterdir()), [])

    @patch.object(offline_demo, "judge_problem")
    def test_existing_output_is_never_overwritten(self, judge):
        self.output.mkdir()
        original = self.output / "keep.txt"
        original.write_text("keep")
        with self.assertRaisesRegex(ValueError, "이미 있습니다"):
            offline_demo.run_offline_demo(self.root, self.output)
        self.assertEqual(original.read_text(), "keep")
        self.assertEqual(list(self.output.iterdir()), [original])
        judge.assert_not_called()

    @patch.object(offline_demo, "judge_problem")
    def test_output_cannot_enter_real_repository_trees(self, judge):
        for relative in ("results/benchmark/new", "data/new", "src/new", "new"):
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, "results/demo"):
                offline_demo.run_offline_demo(self.root, self.root / relative)
        self.assertEqual(list(self.root.iterdir()), [])
        judge.assert_not_called()

    @patch.object(offline_demo, "judge_problem")
    def test_symlink_to_protected_tree_cannot_bypass_output_boundary(self, judge):
        protected = self.root / "results/benchmark"
        protected.mkdir(parents=True)
        alias = self.root.parent / "alias"
        alias.symlink_to(protected, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "results/demo"):
            offline_demo.run_offline_demo(self.root, alias / "new")
        self.assertEqual(list(protected.iterdir()), [])
        judge.assert_not_called()

    @patch.object(offline_demo, "judge_problem", side_effect=mock_judgment)
    def test_default_runs_get_separate_directories(self, judge):
        with contextlib.redirect_stdout(io.StringIO()):
            first = offline_demo.run_offline_demo(self.root)
            second = offline_demo.run_offline_demo(self.root)
        self.assertNotEqual(first, second)
        self.assertTrue(first.is_relative_to(self.root / "results/demo/offline"))
        self.assertTrue((first / "report.json").is_file())
        self.assertTrue((second / "report.json").is_file())

    @patch.object(offline_demo, "judge_problem")
    @patch.object(offline_demo, "extract_python_code", return_value="unexpected code")
    def test_only_exact_trusted_fixture_code_can_run(self, extract, judge):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "실행하지 않았습니다"):
            offline_demo.run_offline_demo(self.root, self.output)
        judge.assert_not_called()
        self.assertFalse((self.output / "correct/candidate.py").exists())

    @patch.object(offline_demo, "judge_problem", return_value={
        "status": "TLE", "passed_cases": 0, "total_cases": 3, "max_case_seconds": 2,
    })
    def test_unexpected_verdict_is_saved_and_reported_as_failure(self, judge):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "예상한 합성"):
            offline_demo.run_offline_demo(self.root, self.output)
        report = json.loads((self.output / "report.json").read_text())
        self.assertFalse(report["expected_outcomes_matched"])
        self.assertEqual(report["verdict_counts"], {"TLE": 2, "NO_CODE": 1})


@unittest.skipUnless(
    os.environ.get("LLM_EVAL_RUN_PROCESS_TESTS") == "1",
    "set LLM_EVAL_RUN_PROCESS_TESTS=1 for trusted synthetic subprocess tests",
)
class OfflineDemoProcessTests(unittest.TestCase):
    def test_real_synthetic_end_to_end_without_credentials_or_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "checkout"
            root.mkdir()
            output = Path(temporary) / "output"
            with patch.dict(os.environ, {}, clear=True), \
                    patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                    contextlib.redirect_stdout(io.StringIO()):
                offline_demo.run_offline_demo(root, output)
            report = json.loads((output / "report.json").read_text())
            self.assertTrue(report["expected_outcomes_matched"])
            self.assertEqual(report["verdict_counts"], {"AC": 1, "WA": 1, "NO_CODE": 1})
            correct = json.loads((output / "correct/judge.json").read_text())
            wrong = json.loads((output / "wrong/judge.json").read_text())
            self.assertEqual((correct["passed_cases"], correct["total_cases"]), (3, 3))
            self.assertEqual((wrong["passed_cases"], wrong["total_cases"]), (1, 3))
            self.assertEqual(list(root.iterdir()), [])
