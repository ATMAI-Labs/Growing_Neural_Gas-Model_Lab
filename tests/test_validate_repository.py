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
        manifest["implementation"]["entrypoint"] = "../../outside.py"
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

        findings = validate_repository(root)

        self.assertTrue(any(item.code == "EXP013" for item in findings))


if __name__ == "__main__":
    unittest.main()
