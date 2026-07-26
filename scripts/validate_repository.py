#!/usr/bin/env python3
"""Fast, dependency-free checks for the public lab structure."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LAB_ID = re.compile(r"^[0-9]{3}-[a-z0-9]+(?:-[a-z0-9]+)*$")
EXPERIMENT_ID = re.compile(r"^exp-[0-9]{8}-[0-9a-f]{8}$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HANDLE = re.compile(r"^@[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
MAX_FILE_BYTES = 5 * 1024 * 1024

REQUIRED_FILES = {
    ".github/CODEOWNERS",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
}
BANNED_NAMES = {".env", "id_dsa", "id_ecdsa", "id_ed25519", "id_rsa"}
BANNED_SUFFIXES = {
    ".7z",
    ".ckpt",
    ".dmg",
    ".exe",
    ".gz",
    ".h5",
    ".hdf5",
    ".joblib",
    ".key",
    ".onnx",
    ".p12",
    ".pem",
    ".pfx",
    ".pkl",
    ".pt",
    ".pth",
    ".tar",
    ".zip",
}
LAB_FIELDS = {"id", "title", "status", "owner", "question"}
EXPERIMENT_FIELDS = {
    "id",
    "slug",
    "lab",
    "title",
    "status",
    "owner",
    "authors",
    "hypothesis",
    "entrypoint",
    "references",
}


@dataclass(frozen=True, order=True)
class Finding:
    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} {self.path}: {self.message}"


def add(
    findings: list[Finding], code: str, path: Path | str, message: str
) -> None:
    findings.append(Finding(code, Path(path).as_posix(), message))


def repository_files(root: Path) -> list[Path]:
    """Include tracked and visible untracked files, but exclude ignored work."""

    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return [
            root / item.decode("utf-8")
            for item in result.stdout.split(b"\0")
            if item
        ]
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    ]


def load_json(
    path: Path, root: Path, findings: list[Finding]
) -> dict[str, Any] | None:
    relative = path.relative_to(root)
    if not path.is_file():
        add(findings, "JSON001", relative, "required manifest is missing")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        add(findings, "JSON002", relative, f"cannot parse JSON: {error}")
        return None
    if not isinstance(value, dict):
        add(findings, "JSON003", relative, "manifest must be a JSON object")
        return None
    return value


def validate_fields(
    manifest: dict[str, Any],
    required: set[str],
    path: Path,
    root: Path,
    findings: list[Finding],
) -> None:
    missing = sorted(required - manifest.keys())
    if missing:
        add(
            findings,
            "FIELD001",
            path.relative_to(root),
            f"missing fields: {', '.join(missing)}",
        )


def valid_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_owner(
    value: Any, path: Path, root: Path, findings: list[Finding]
) -> None:
    if not isinstance(value, str) or not HANDLE.fullmatch(value):
        add(
            findings,
            "OWNER001",
            path.relative_to(root),
            "owner must be one public GitHub handle such as @example",
        )


def validate_authors(
    value: Any, path: Path, root: Path, findings: list[Finding]
) -> None:
    if (
        not isinstance(value, list)
        or not value
        or any(
            not isinstance(author, str) or not HANDLE.fullmatch(author)
            for author in value
        )
    ):
        add(
            findings,
            "AUTHOR001",
            path.relative_to(root),
            "authors must contain at least one public GitHub handle",
        )


def validate_experiment(
    directory: Path, lab_id: str, root: Path, findings: list[Finding]
) -> None:
    relative = directory.relative_to(root)
    if not (directory / "README.md").is_file():
        add(findings, "EXP001", relative, "README.md is missing")

    path = directory / "experiment.json"
    manifest = load_json(path, root, findings)
    if manifest is None:
        return
    validate_fields(manifest, EXPERIMENT_FIELDS, path, root, findings)

    experiment_id = manifest.get("id")
    slug = manifest.get("slug")
    if not isinstance(experiment_id, str) or not EXPERIMENT_ID.fullmatch(
        experiment_id
    ):
        add(findings, "EXP002", path.relative_to(root), "invalid experiment id")
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        add(findings, "EXP003", path.relative_to(root), "invalid experiment slug")
    if isinstance(experiment_id, str) and isinstance(slug, str):
        expected = f"{experiment_id}-{slug}"
        if directory.name != expected:
            add(findings, "EXP004", relative, f"directory must be named {expected}")

    if manifest.get("lab") != lab_id:
        add(findings, "EXP005", path.relative_to(root), "lab must match its parent")
    if manifest.get("status") not in {
        "planned",
        "running",
        "complete",
        "failed",
        "inconclusive",
        "archived",
    }:
        add(findings, "EXP006", path.relative_to(root), "invalid experiment status")
    for field in ("title", "hypothesis"):
        if not valid_text(manifest.get(field)):
            add(
                findings,
                "EXP007",
                path.relative_to(root),
                f"{field} must be non-empty",
            )
    validate_owner(manifest.get("owner"), path, root, findings)
    validate_authors(manifest.get("authors"), path, root, findings)
    if not isinstance(manifest.get("references"), list):
        add(findings, "EXP008", path.relative_to(root), "references must be a list")

    entrypoint = manifest.get("entrypoint")
    if entrypoint is not None:
        unsafe = (
            not isinstance(entrypoint, str)
            or Path(entrypoint).is_absolute()
            or ".." in Path(entrypoint).parts
        )
        if unsafe:
            add(
                findings,
                "EXP013",
                path.relative_to(root),
                "entrypoint must be a safe relative path or null",
            )
        elif not (directory / entrypoint).is_file():
            add(
                findings,
                "EXP014",
                path.relative_to(root),
                f"entrypoint does not exist: {entrypoint}",
            )


def validate_lab(directory: Path, root: Path, findings: list[Finding]) -> int:
    relative = directory.relative_to(root)
    if not LAB_ID.fullmatch(directory.name):
        add(findings, "LAB001", relative, "lab name must be NNN-kebab-case")
    if not (directory / "README.md").is_file():
        add(findings, "LAB002", relative, "README.md is missing")

    path = directory / "lab.json"
    manifest = load_json(path, root, findings)
    lab_id = directory.name
    if manifest is not None:
        validate_fields(manifest, LAB_FIELDS, path, root, findings)
        if manifest.get("id") != directory.name:
            add(findings, "LAB003", path.relative_to(root), "id must match directory")
        if manifest.get("status") not in {
            "planned",
            "active",
            "complete",
            "archived",
        }:
            add(findings, "LAB004", path.relative_to(root), "invalid lab status")
        for field in ("title", "question"):
            if not valid_text(manifest.get(field)):
                add(
                    findings,
                    "LAB005",
                    path.relative_to(root),
                    f"{field} must be non-empty",
                )
        validate_owner(manifest.get("owner"), path, root, findings)
        if isinstance(manifest.get("id"), str):
            lab_id = manifest["id"]

    experiments = directory / "experiments"
    if not experiments.is_dir():
        add(findings, "LAB006", relative, "experiments directory is missing")
        return 0
    count = 0
    for experiment in sorted(experiments.iterdir()):
        if experiment.is_dir():
            count += 1
            validate_experiment(experiment, lab_id, root, findings)
    return count


def validate_files(root: Path, findings: list[Finding]) -> None:
    for path in repository_files(root):
        relative = path.relative_to(root)
        if path.is_symlink():
            add(findings, "FILE001", relative, "symbolic links are not allowed")
            continue
        if path.name in BANNED_NAMES or (
            path.name.startswith(".env") and path.name != ".env.example"
        ):
            add(findings, "FILE001", relative, "secret-bearing file is prohibited")
        if path.suffix.lower() in BANNED_SUFFIXES:
            add(findings, "FILE002", relative, "artifact type is prohibited")
        if path.is_file() and path.stat().st_size > MAX_FILE_BYTES:
            add(findings, "FILE003", relative, "file exceeds 5 MiB")


def validate_repository(root: Path = REPOSITORY_ROOT) -> list[Finding]:
    root = root.resolve()
    findings: list[Finding] = []
    for required in REQUIRED_FILES:
        if not (root / required).is_file():
            add(findings, "ROOT001", required, "required public-repo file is missing")
    validate_files(root, findings)

    labs = root / "labs"
    if not labs.is_dir():
        add(findings, "ROOT002", "labs", "labs directory is missing")
    else:
        lab_count = 0
        experiment_count = 0
        for directory in sorted(labs.iterdir()):
            if directory.is_dir():
                lab_count += 1
                experiment_count += validate_lab(directory, root, findings)
        if lab_count == 0:
            add(findings, "ROOT003", "labs", "at least one lab is required")
        if experiment_count == 0:
            add(findings, "ROOT004", "labs", "at least one experiment is required")
    return sorted(set(findings))


def main() -> int:
    if len(sys.argv) != 1:
        print("usage: python3 scripts/validate_repository.py", file=sys.stderr)
        return 2
    findings = validate_repository()
    if findings:
        print(f"Repository validation failed with {len(findings)} finding(s):")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Repository validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
