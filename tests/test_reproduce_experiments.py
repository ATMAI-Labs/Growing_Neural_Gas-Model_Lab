from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.reproduce_experiments import (
    REPOSITORY_ROOT, ReproductionError, compare_results, load_registry,
    main, verify_frozen_files,
)


class ReproductionTests(unittest.TestCase):
    def fixture(self) -> tuple[Path, dict]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repo"
        directory = "labs/001-fixture/experiments/exp-20260101-1234abcd-fixture"
        experiment = root / directory
        (experiment / "results").mkdir(parents=True)
        (root / "src").mkdir()
        (root / "src/engine.py").write_text("# Frozen reference\n")
        result = {"experiment_id": "exp-20260101-1234abcd", "environment": {"host": "old"},
                  "metric": 0.125, "definitions": {"timing_seconds": "wall clock"},
                  "datasets": [{"name": "fixture", "timing_seconds": 1.0}]}
        (experiment / "results/result.json").write_text(json.dumps(result))
        # A real subprocess fixture proves --stdout and interpreter invocation.
        (experiment / "run.py").write_text(
            "import json,sys\nfrom pathlib import Path\n"
            "assert sys.argv[1:] == ['--stdout']\n"
            "result=json.loads((Path(__file__).parent/'results/result.json').read_text())\n"
            "result['environment']={'host':'new'}\n"
            "print(json.dumps(result))\n"
        )
        (experiment / "experiment.json").write_text(json.dumps({
            "id": "exp-20260101-1234abcd", "status": "complete", "entrypoint": "run.py"}))
        (experiment / "README.md").write_text("Frozen fixture\n")
        registry = {
            "schema": "atmai.gng.reproducibility/v1",
            "engines": {"canonical-gng-v1": {"path": "src/engine.py", "sha256": self.digest(root / "src/engine.py")}},
            "experiments": [{"id": "exp-20260101-1234abcd", "directory": directory,
                             "entrypoint": "run.py", "result": "results/result.json",
                             "engine": "canonical-gng-v1",
                             "files": {p.relative_to(root).as_posix(): self.digest(p)
                                       for p in experiment.rglob("*") if p.is_file()},
                             "ignore_json_paths": ["/environment", "/datasets/0/timing_seconds"]}],
        }
        self.save_registry(root, registry)
        return root, registry

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def save_registry(root: Path, registry: dict) -> None:
        (root / "reproducibility.json").write_text(json.dumps(registry))

    def invoke(self, root: Path, args: list[str]) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = main(args, root=root)
        return status, output.getvalue()

    def test_current_frozen_registry_matches_all_bytes(self) -> None:
        registry = load_registry(REPOSITORY_ROOT)
        self.assertEqual(verify_frozen_files(REPOSITORY_ROOT, registry), [])
        self.assertTrue({"exp-20260727-ee260fe9", "exp-20260727-eee720cf"}.issubset(
            {item["id"] for item in registry["experiments"]}))

    def test_exact_metric_comparison_reports_json_pointer(self) -> None:
        expected = {"datasets": [{"metric": 0.125}]}
        actual = copy.deepcopy(expected)
        actual["datasets"][0]["metric"] += 1e-12
        differences = compare_results(expected, actual, [])
        self.assertEqual(len(differences), 1)
        self.assertIn("/datasets/0/metric", differences[0])
        self.assertTrue(compare_results({"value": 1}, {"value": True}, []))
        self.assertTrue(compare_results({"value": 1}, {"value": 1.0}, []))

    def test_ignores_only_exact_host_paths_without_mutating_inputs(self) -> None:
        expected = {"environment": {"python": "3.9"}, "timing_seconds": 1.0,
                    "tracemalloc_peak_bytes": 100,
                    "datasets": [{"timing_seconds": 2.0, "metric": 0.25}],
                    "definitions": {"timing_seconds": "wall clock"}}
        actual = copy.deepcopy(expected)
        actual["environment"] = {"python": "3.14", "different": True}
        actual["timing_seconds"] = 3.0
        actual["tracemalloc_peak_bytes"] = 200
        actual["datasets"][0]["timing_seconds"] = 4.0
        ignored = ["/environment", "/timing_seconds", "/tracemalloc_peak_bytes",
                   "/datasets/0/timing_seconds"]
        before = copy.deepcopy((expected, actual))
        self.assertEqual(compare_results(expected, actual, ignored), [])
        self.assertEqual((expected, actual), before)
        actual["definitions"]["timing_seconds"] = "changed definition"
        self.assertIn("/definitions/timing_seconds", compare_results(expected, actual, ignored)[0])
        actual["datasets"].append({"timing_seconds": 5.0})
        self.assertTrue(any("items" in d for d in compare_results(expected, actual, ignored)))

    def test_missing_ignored_field_still_fails(self) -> None:
        self.assertTrue(compare_results({"environment": {}}, {}, ["/environment"]))
        with self.assertRaises(ReproductionError):
            compare_results({"metric": 1}, {"metric": 2}, ["/metric"])

    def test_frozen_hash_failure_prevents_runner_execution(self) -> None:
        root, registry = self.fixture()
        (root / "src/engine.py").write_text("# Modified\n")
        self.assertTrue(any("SHA-256 mismatch" in s for s in verify_frozen_files(root, registry)))
        with patch("scripts.reproduce_experiments.subprocess.run") as run:
            status, output = self.invoke(root, [])
        run.assert_not_called()
        self.assertEqual(status, 1)
        self.assertIn("SHA-256 mismatch", output)

    def test_all_experiment_files_must_be_registered(self) -> None:
        root, registry = self.fixture()
        directory = root / registry["experiments"][0]["directory"]
        (directory / "extra.txt").write_text("unregistered")
        self.assertTrue(any("unregistered experiment file" in s
                            for s in verify_frozen_files(root, registry)))
        (directory / "README.md").unlink()
        self.assertTrue(any("cannot verify" in s for s in verify_frozen_files(root, registry)))

    def test_git_inventory_checks_untracked_files_before_staging(self) -> None:
        root, registry = self.fixture()
        subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True)
        self.assertEqual(verify_frozen_files(root, registry), [])
        directory = root / registry["experiments"][0]["directory"]
        (directory / "untracked-helper.py").write_text("# Additional source\n")
        self.assertTrue(any("unregistered experiment file" in s
                            for s in verify_frozen_files(root, registry)))

    def test_registry_rejects_unsafe_and_inconsistent_paths(self) -> None:
        root, registry = self.fixture()
        for field, value in [("directory", "../outside"), ("entrypoint", "../run.py"),
                             ("entrypoint", "/tmp/run.py"), ("result", "results//result.json"),
                             ("entrypoint", "./run.py"), ("engine", "missing")]:
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(registry)
                changed["experiments"][0][field] = value
                self.save_registry(root, changed)
                with self.assertRaises(ReproductionError):
                    load_registry(root)
        changed = copy.deepcopy(registry)
        changed["experiments"][0]["ignore_json_paths"] = ["/metric"]
        self.save_registry(root, changed)
        with self.assertRaises(ReproductionError):
            load_registry(root)
        changed = copy.deepcopy(registry)
        changed["engines"]["canonical-gng-v1"]["sha256"] = "not a hash"
        self.save_registry(root, changed)
        with self.assertRaises(ReproductionError):
            load_registry(root)
        self.save_registry(root, registry)
        engine = root / "src/engine.py"
        target = root.parent / "outside.py"
        target.write_bytes(engine.read_bytes())
        engine.unlink()
        engine.symlink_to(target)
        with self.assertRaises(ReproductionError):
            load_registry(root)

    def test_runner_uses_stdout_without_repository_writes(self) -> None:
        root, _ = self.fixture()
        before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        status, output = self.invoke(root, [])
        self.assertEqual(status, 0, output)
        self.assertIn("exact deterministic match", output)
        after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_cli_rejects_repo_and_symlink_output_before_execution(self) -> None:
        root, _ = self.fixture()
        alias = root.parent / "alias"
        alias.symlink_to(root, target_is_directory=True)
        for path in (root, root / "generated", alias / "generated"):
            with self.subTest(path=path):
                with patch("scripts.reproduce_experiments.subprocess.run") as run:
                    status, output = self.invoke(root, ["--output-dir", str(path)])
                run.assert_not_called()
                self.assertEqual(status, 1)
                self.assertIn("outside the repository", output)

    def test_output_retains_fresh_result_and_never_overwrites(self) -> None:
        root, registry = self.fixture()
        output_dir = root.parent / "fresh"
        args = ["--output-dir", str(output_dir)]
        status, output = self.invoke(root, args)
        self.assertEqual(status, 0, output)
        path = output_dir / (registry["experiments"][0]["id"] + ".json")
        self.assertEqual(json.loads(path.read_text())["environment"], {"host": "new"})
        before = path.read_bytes()
        with patch("scripts.reproduce_experiments.subprocess.run") as run:
            status, output = self.invoke(root, args)
        run.assert_not_called()
        self.assertEqual(status, 1)
        self.assertIn("refusing to overwrite", output)
        self.assertEqual(path.read_bytes(), before)

    def test_cli_reports_deterministic_mismatch(self) -> None:
        root, registry = self.fixture()
        completed = subprocess.CompletedProcess([], 0, json.dumps({
            "experiment_id": "exp-20260101-1234abcd", "environment": {},
            "metric": 0.5, "definitions": {"timing_seconds": "wall clock"},
            "datasets": [{"name": "fixture", "timing_seconds": 1.0}]}), "")
        with patch("scripts.reproduce_experiments.subprocess.run", return_value=completed):
            status, output = self.invoke(root, [])
        self.assertEqual(status, 1)
        self.assertIn("/metric: expected 0.125, got 0.5", output)

    def test_invalid_runner_json_and_unknown_ids_fail(self) -> None:
        root, _ = self.fixture()
        status, output = self.invoke(root, ["--experiment", "missing"])
        self.assertEqual(status, 1)
        self.assertIn("unregistered experiments", output)
        for payload in ('{"metric": NaN}', '{"metric":1e999}', '{"metric":1,"metric":2}', 'not JSON'):
            completed = subprocess.CompletedProcess([], 0, payload, "")
            with patch("scripts.reproduce_experiments.subprocess.run", return_value=completed):
                status, output = self.invoke(root, [])
            self.assertEqual(status, 1)
            self.assertIn("invalid JSON", output)


if __name__ == "__main__":
    unittest.main()
