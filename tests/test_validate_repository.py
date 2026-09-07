from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validate_repository import REPOSITORY_ROOT, validate_repository


class RepositoryValidationTests(unittest.TestCase):
    def copy_repository(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "repo"
        shutil.copytree(
            REPOSITORY_ROOT,
            root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        return temporary, root

    def add_experiment(self, root: Path, **overrides: object) -> Path:
        """Add a new claim without rewriting one of the frozen experiments."""

        manifest = {
            "id": "exp-20260907-1234abcd",
            "slug": "validation-fixture",
            "lab": "002-controlled-drift",
            "title": "Repository validation fixture",
            "status": "planned",
            "owner": "@example",
            "authors": ["@example"],
            "hypothesis": "A planned experiment can precede runnable evidence.",
            "entrypoint": None,
            "references": [],
        }
        manifest.update(overrides)
        directory = (
            root
            / "labs"
            / "002-controlled-drift"
            / "experiments"
            / "exp-20260907-1234abcd-validation-fixture"
        )
        directory.mkdir()
        (directory / "README.md").write_text("Planned validation fixture.\n")
        (directory / "run.py").write_text("print('fixture')\n")
        path = directory / "experiment.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return path

    def test_current_repository_is_valid(self) -> None:
        self.assertEqual(validate_repository(REPOSITORY_ROOT), [])

    def test_rejects_mismatched_experiment_directory(self) -> None:
        temporary, root = self.copy_repository()
        self.addCleanup(temporary.cleanup)
        experiment = next(
            path
            for path in (root / "labs").glob("*/experiments/exp-*")
            if path.is_dir()
        )
        experiment.rename(experiment.with_name(f"{experiment.name}-wrong"))

        findings = validate_repository(root)

        self.assertTrue(any(item.code == "EXP004" for item in findings))

    def test_rejects_model_artifacts(self) -> None:
        temporary, root = self.copy_repository()
        self.addCleanup(temporary.cleanup)
        artifact = root / "labs" / "model.ckpt"
        artifact.write_bytes(b"not-a-real-model")

        findings = validate_repository(root)

        self.assertTrue(any(item.code == "FILE002" for item in findings))

    def test_rejects_manifest_path_escape(self) -> None:
        temporary, root = self.copy_repository()
        self.addCleanup(temporary.cleanup)
        manifest_path = next((root / "labs").glob("*/experiments/*/experiment.json"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["entrypoint"] = "../../outside.py"
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

        findings = validate_repository(root)

        self.assertTrue(any(item.code == "EXP013" for item in findings))

    def test_accepts_planned_template_without_entrypoint_or_references(self) -> None:
        temporary, root = self.copy_repository()
        self.addCleanup(temporary.cleanup)
        self.add_experiment(root)

        self.assertEqual(validate_repository(root), [])

    def test_rejects_complete_experiment_without_entrypoint(self) -> None:
        temporary, root = self.copy_repository()
        self.addCleanup(temporary.cleanup)
        self.add_experiment(
            root, status="complete", references=["https://example.org/paper"]
        )

        findings = validate_repository(root)

        self.assertTrue(any(item.code == "EXP015" for item in findings))

    def test_rejects_complete_experiment_without_references(self) -> None:
        temporary, root = self.copy_repository()
        self.addCleanup(temporary.cleanup)
        self.add_experiment(root, status="complete", entrypoint="run.py")

        findings = validate_repository(root)

        self.assertTrue(any(item.code == "EXP010" for item in findings))

    def test_rejects_malformed_reference_urls(self) -> None:
        for reference in (
            42,
            "",
            "a paper title",
            "ftp://example.org/paper",
            "https://",
            "https://bad host/paper",
            "https://example.org:invalid/paper",
            "https://example.org/\u0000paper",
        ):
            with self.subTest(reference=reference):
                temporary, root = self.copy_repository()
                try:
                    self.add_experiment(root, references=[reference])
                    findings = validate_repository(root)
                    self.assertTrue(any(item.code == "EXP009" for item in findings))
                finally:
                    temporary.cleanup()

    def test_rejects_unregistered_complete_experiment(self) -> None:
        temporary, root = self.copy_repository()
        self.addCleanup(temporary.cleanup)
        self.add_experiment(
            root,
            status="complete",
            entrypoint="run.py",
            references=["https://example.org/paper"],
        )

        findings = validate_repository(root)

        self.assertEqual([item.code for item in findings], ["EXP016"])

    def test_rejects_tampered_frozen_evidence(self) -> None:
        temporary, root = self.copy_repository()
        self.addCleanup(temporary.cleanup)
        result = next((root / "labs").glob("*/experiments/*/results/*.json"))
        result.write_text(result.read_text(encoding="utf-8") + "\n", encoding="utf-8")

        findings = validate_repository(root)

        self.assertTrue(any(item.code == "REPRO002" for item in findings))

    def test_accepts_failed_and_inconclusive_without_executable(self) -> None:
        # A failure before execution must be reportable without inventing a result.
        for status in ("failed", "inconclusive"):
            with self.subTest(status=status):
                temporary, root = self.copy_repository()
                try:
                    self.add_experiment(root, status=status)
                    self.assertEqual(validate_repository(root), [])
                finally:
                    temporary.cleanup()

    def test_rejects_invalid_predecessors(self) -> None:
        cases = (
            ("exp-20260727-ee260fe9", "EXP018"),
            ([42], "EXP018"),
            (["not-an-experiment-id"], "EXP018"),
            (["exp-20260907-abcdef12"], "EXP019"),
            (["exp-20260907-1234abcd"], "EXP019"),
            (["exp-20260727-ee260fe9", "exp-20260727-ee260fe9"], "EXP018"),
        )
        for predecessors, code in cases:
            with self.subTest(predecessors=predecessors):
                temporary, root = self.copy_repository()
                try:
                    self.add_experiment(root, predecessors=predecessors)
                    findings = validate_repository(root)
                    self.assertTrue(any(item.code == code for item in findings))
                finally:
                    temporary.cleanup()

    def test_accepts_resolved_predecessor(self) -> None:
        temporary, root = self.copy_repository()
        self.addCleanup(temporary.cleanup)
        self.add_experiment(root, predecessors=["exp-20260727-eee720cf"])

        self.assertEqual(validate_repository(root), [])

    def test_reports_invalid_status_type_without_crashing(self) -> None:
        temporary, root = self.copy_repository()
        self.addCleanup(temporary.cleanup)
        self.add_experiment(root, status=["planned"])
        lab_path = root / "labs" / "002-controlled-drift" / "lab.json"
        lab = json.loads(lab_path.read_text(encoding="utf-8"))
        lab["status"] = ["active"]
        lab_path.write_text(json.dumps(lab), encoding="utf-8")

        findings = validate_repository(root)

        self.assertTrue(any(item.code == "EXP006" for item in findings))
        self.assertTrue(any(item.code == "LAB004" for item in findings))


if __name__ == "__main__":
    unittest.main()
