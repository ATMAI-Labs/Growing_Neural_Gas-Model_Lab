#!/usr/bin/env python3
"""Validate the public research-lab contract without third-party dependencies."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LAB_ID = re.compile(r"^[0-9]{3}-[a-z0-9]+(?:-[a-z0-9]+)*$")
EXPERIMENT_ID = re.compile(r"^exp-([0-9]{8})-([0-9a-f]{8})$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GITHUB_HANDLE = re.compile(
    r"^@[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$"
)
MAX_FILE_BYTES = 5 * 1024 * 1024

REQUIRED_ROOT_FILES = {
    ".github/CODEOWNERS",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "GOVERNANCE.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "SUPPORT.md",
}
ALLOWED_ROOT_FILES = {
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "CITATION.cff",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "GOVERNANCE.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "SUPPORT.md",
}
ALLOWED_ROOT_DIRECTORIES = {
    ".github",
    "datasets",
    "docs",
    "labs",
    "schemas",
    "scripts",
    "src",
    "templates",
    "tests",
}
BANNED_FILENAMES = {
    ".env",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
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
LAB_KEYS = {
    "$schema",
    "schema_version",
    "id",
    "title",
    "status",
    "research_question",
    "owners",
    "created",
    "updated",
    "license",
    "references",
}
EXPERIMENT_KEYS = {
    "$schema",
    "schema_version",
    "id",
    "slug",
    "lab_id",
    "title",
    "status",
    "research_type",
    "hypothesis",
    "authors",
    "created",
    "updated",
    "predecessors",
    "implementation",
    "data_sources",
    "reproducibility",
    "metrics",
    "provenance",
}


@dataclass(frozen=True, order=True)
class Finding:
    """One stable validation diagnostic."""

    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} {self.path}: {self.message}"


def _add(
    findings: list[Finding], code: str, path: Path | str, message: str
) -> None:
    findings.append(Finding(code, Path(path).as_posix(), message))


def _repository_files(root: Path) -> list[Path]:
    """Return tracked and visible untracked files, excluding ignored local work."""

    command = [
        "git",
        "-C",
        str(root),
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ]
    result = subprocess.run(command, capture_output=True, check=False)
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


def _load_json(
    path: Path, root: Path, findings: list[Finding]
) -> dict[str, Any] | None:
    relative = path.relative_to(root)
    if not path.is_file():
        _add(findings, "JSON001", relative, "required JSON manifest is missing")
        return None

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _add(findings, "JSON002", relative, f"cannot parse JSON: {error}")
        return None

    if not isinstance(value, dict):
        _add(findings, "JSON003", relative, "manifest root must be an object")
        return None
    return value


def _non_empty_string(
    value: Any, field: str, path: Path, root: Path, findings: list[Finding]
) -> bool:
    if not isinstance(value, str) or not value.strip():
        _add(
            findings,
            "FIELD001",
            path.relative_to(root),
            f"{field} must be a non-empty string",
        )
        return False
    return True


def _validate_date_pair(
    manifest: dict[str, Any],
    path: Path,
    root: Path,
    findings: list[Finding],
) -> None:
    parsed: dict[str, date] = {}
    for field in ("created", "updated"):
        value = manifest.get(field)
        try:
            parsed[field] = date.fromisoformat(value)
        except (TypeError, ValueError):
            _add(
                findings,
                "DATE001",
                path.relative_to(root),
                f"{field} must be an ISO date in YYYY-MM-DD form",
            )
    if set(parsed) == {"created", "updated"} and parsed["updated"] < parsed["created"]:
        _add(
            findings,
            "DATE002",
            path.relative_to(root),
            "updated cannot be earlier than created",
        )


def _validate_people(
    manifest: dict[str, Any],
    field: str,
    path: Path,
    root: Path,
    findings: list[Finding],
) -> None:
    people = manifest.get(field)
    if not isinstance(people, list) or not people:
        _add(
            findings,
            "OWNER001",
            path.relative_to(root),
            f"{field} must contain at least one GitHub handle",
        )
        return
    if len(people) != len(set(map(str, people))):
        _add(
            findings,
            "OWNER002",
            path.relative_to(root),
            f"{field} must not contain duplicates",
        )
    for person in people:
        if not isinstance(person, str) or not GITHUB_HANDLE.fullmatch(person):
            _add(
                findings,
                "OWNER003",
                path.relative_to(root),
                f"invalid GitHub handle in {field}: {person!r}",
            )


def _validate_keys(
    manifest: dict[str, Any],
    allowed: set[str],
    path: Path,
    root: Path,
    findings: list[Finding],
) -> None:
    missing = sorted(allowed - manifest.keys())
    extra = sorted(manifest.keys() - allowed)
    if missing:
        _add(
            findings,
            "FIELD002",
            path.relative_to(root),
            f"missing fields: {', '.join(missing)}",
        )
    if extra:
        _add(
            findings,
            "FIELD003",
            path.relative_to(root),
            f"unknown fields: {', '.join(extra)}",
        )


def _validate_lab(
    lab_dir: Path, root: Path, findings: list[Finding]
) -> tuple[str | None, int]:
    relative = lab_dir.relative_to(root)
    if not LAB_ID.fullmatch(lab_dir.name):
        _add(
            findings,
            "LAB001",
            relative,
            "lab directory must match NNN-lowercase-kebab-case",
        )

    if not (lab_dir / "README.md").is_file():
        _add(findings, "LAB002", relative, "lab README.md is missing")

    manifest_path = lab_dir / "lab.json"
    manifest = _load_json(manifest_path, root, findings)
    lab_id: str | None = None
    if manifest is not None:
        _validate_keys(manifest, LAB_KEYS, manifest_path, root, findings)
        lab_id = manifest.get("id") if isinstance(manifest.get("id"), str) else None
        if lab_id != lab_dir.name:
            _add(
                findings,
                "LAB003",
                manifest_path.relative_to(root),
                "manifest id must equal the lab directory name",
            )
        if manifest.get("$schema") != "../../schemas/lab.schema.json":
            _add(
                findings,
                "LAB004",
                manifest_path.relative_to(root),
                "$schema must point to ../../schemas/lab.schema.json",
            )
        if manifest.get("schema_version") != 1:
            _add(
                findings,
                "LAB005",
                manifest_path.relative_to(root),
                "schema_version must be 1",
            )
        if manifest.get("status") not in {
            "proposed",
            "active",
            "completed",
            "archived",
        }:
            _add(
                findings,
                "LAB006",
                manifest_path.relative_to(root),
                "invalid lab status",
            )
        for field in ("title", "research_question", "license"):
            _non_empty_string(
                manifest.get(field), field, manifest_path, root, findings
            )
        _validate_people(manifest, "owners", manifest_path, root, findings)
        _validate_date_pair(manifest, manifest_path, root, findings)
        if not isinstance(manifest.get("references"), list):
            _add(
                findings,
                "LAB007",
                manifest_path.relative_to(root),
                "references must be an array",
            )

    experiments_dir = lab_dir / "experiments"
    if not experiments_dir.is_dir():
        _add(findings, "LAB008", relative, "experiments directory is missing")
        return lab_id, 0

    experiment_count = 0
    for experiment_dir in sorted(experiments_dir.iterdir()):
        if not experiment_dir.is_dir():
            continue
        experiment_count += 1
        _validate_experiment(experiment_dir, lab_id, root, findings)
    if experiment_count == 0:
        _add(findings, "LAB009", relative, "lab must contain an experiment")
    return lab_id, experiment_count


def _validate_experiment(
    experiment_dir: Path,
    lab_id: str | None,
    root: Path,
    findings: list[Finding],
) -> None:
    relative = experiment_dir.relative_to(root)
    if not (experiment_dir / "README.md").is_file():
        _add(findings, "EXP001", relative, "experiment README.md is missing")

    manifest_path = experiment_dir / "experiment.json"
    manifest = _load_json(manifest_path, root, findings)
    if manifest is None:
        return

    _validate_keys(manifest, EXPERIMENT_KEYS, manifest_path, root, findings)
    experiment_id = manifest.get("id")
    slug = manifest.get("slug")
    match = (
        EXPERIMENT_ID.fullmatch(experiment_id)
        if isinstance(experiment_id, str)
        else None
    )
    if match is None:
        _add(
            findings,
            "EXP002",
            manifest_path.relative_to(root),
            "id must match exp-YYYYMMDD-8hex",
        )
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        _add(
            findings,
            "EXP003",
            manifest_path.relative_to(root),
            "slug must be lowercase kebab-case",
        )
    elif isinstance(experiment_id, str):
        expected_directory = f"{experiment_id}-{slug}"
        if experiment_dir.name != expected_directory:
            _add(
                findings,
                "EXP004",
                relative,
                f"directory must be named {expected_directory}",
            )

    if manifest.get("lab_id") != lab_id:
        _add(
            findings,
            "EXP005",
            manifest_path.relative_to(root),
            "lab_id must equal the parent lab manifest id",
        )
    if manifest.get("$schema") != "../../../../schemas/experiment.schema.json":
        _add(
            findings,
            "EXP006",
            manifest_path.relative_to(root),
            "$schema must point to ../../../../schemas/experiment.schema.json",
        )
    if manifest.get("schema_version") != 1:
        _add(
            findings,
            "EXP007",
            manifest_path.relative_to(root),
            "schema_version must be 1",
        )
    if manifest.get("status") not in {
        "proposed",
        "active",
        "completed",
        "inconclusive",
        "failed",
        "archived",
    }:
        _add(
            findings,
            "EXP008",
            manifest_path.relative_to(root),
            "invalid experiment status",
        )
    if manifest.get("research_type") not in {
        "replication",
        "benchmark",
        "ablation",
        "extension",
        "exploratory",
    }:
        _add(
            findings,
            "EXP009",
            manifest_path.relative_to(root),
            "invalid research_type",
        )
    for field in ("title", "hypothesis"):
        _non_empty_string(manifest.get(field), field, manifest_path, root, findings)
    _validate_people(manifest, "authors", manifest_path, root, findings)
    _validate_date_pair(manifest, manifest_path, root, findings)

    created = manifest.get("created")
    if match is not None and isinstance(created, str):
        expected_date = match.group(1)
        if created.replace("-", "") != expected_date:
            _add(
                findings,
                "EXP010",
                manifest_path.relative_to(root),
                "experiment id date must equal created",
            )

    implementation = manifest.get("implementation")
    if not isinstance(implementation, dict):
        _add(
            findings,
            "EXP011",
            manifest_path.relative_to(root),
            "implementation must be an object",
        )
    else:
        expected = {"language", "entrypoint", "environment"}
        if set(implementation) != expected:
            _add(
                findings,
                "EXP012",
                manifest_path.relative_to(root),
                "implementation fields must be language, entrypoint, environment",
            )
        _non_empty_string(
            implementation.get("language"),
            "implementation.language",
            manifest_path,
            root,
            findings,
        )
        for field in ("entrypoint", "environment"):
            value = implementation.get(field)
            if value is not None:
                if not isinstance(value, str) or Path(value).is_absolute() or ".." in Path(value).parts:
                    _add(
                        findings,
                        "EXP013",
                        manifest_path.relative_to(root),
                        f"implementation.{field} must be a safe relative path or null",
                    )
                elif not (experiment_dir / value).is_file():
                    _add(
                        findings,
                        "EXP014",
                        manifest_path.relative_to(root),
                        f"implementation.{field} does not exist: {value}",
                    )

    for field in (
        "predecessors",
        "data_sources",
        "metrics",
        "provenance",
    ):
        if not isinstance(manifest.get(field), list):
            _add(
                findings,
                "EXP015",
                manifest_path.relative_to(root),
                f"{field} must be an array",
            )
    reproducibility = manifest.get("reproducibility")
    if not isinstance(reproducibility, dict):
        _add(
            findings,
            "EXP016",
            manifest_path.relative_to(root),
            "reproducibility must be an object",
        )
    else:
        if set(reproducibility) != {"seed_policy", "commands"}:
            _add(
                findings,
                "EXP017",
                manifest_path.relative_to(root),
                "reproducibility fields must be seed_policy and commands",
            )
        _non_empty_string(
            reproducibility.get("seed_policy"),
            "reproducibility.seed_policy",
            manifest_path,
            root,
            findings,
        )
        if not isinstance(reproducibility.get("commands"), list):
            _add(
                findings,
                "EXP018",
                manifest_path.relative_to(root),
                "reproducibility.commands must be an array",
            )

    if manifest.get("status") in {"active", "completed", "inconclusive", "failed"}:
        if not isinstance(implementation, dict) or not implementation.get("entrypoint"):
            _add(
                findings,
                "EXP019",
                manifest_path.relative_to(root),
                "non-proposed experiments require an entrypoint",
            )
        if (
            not isinstance(reproducibility, dict)
            or not reproducibility.get("commands")
        ):
            _add(
                findings,
                "EXP020",
                manifest_path.relative_to(root),
                "non-proposed experiments require reproduction commands",
            )


def _validate_repository_paths(root: Path, findings: list[Finding]) -> None:
    files = _repository_files(root)
    casefolded: dict[str, Path] = {}

    for path in files:
        relative = path.relative_to(root)
        if path.is_symlink():
            _add(findings, "PATH001", relative, "symbolic links are not allowed")
            continue
        if not path.exists():
            continue

        folded = relative.as_posix().casefold()
        previous = casefolded.get(folded)
        if previous is not None and previous != relative:
            _add(
                findings,
                "PATH002",
                relative,
                f"case-fold collision with {previous.as_posix()}",
            )
        else:
            casefolded[folded] = relative

        if path.name in BANNED_FILENAMES or (
            path.name.startswith(".env") and path.name != ".env.example"
        ):
            _add(findings, "FILE001", relative, "secret-bearing file is prohibited")
        if path.suffix.lower() in BANNED_SUFFIXES:
            _add(
                findings,
                "FILE002",
                relative,
                f"artifact type {path.suffix.lower()} is prohibited",
            )
        try:
            size = path.stat().st_size
        except OSError as error:
            _add(findings, "FILE003", relative, f"cannot inspect file: {error}")
        else:
            if size > MAX_FILE_BYTES:
                _add(
                    findings,
                    "FILE004",
                    relative,
                    f"file exceeds {MAX_FILE_BYTES} bytes",
                )

    for child in root.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir() and child.name not in ALLOWED_ROOT_DIRECTORIES:
            _add(
                findings,
                "ROOT001",
                child.relative_to(root),
                "top-level directory is not allowlisted; add an ADR first",
            )
        if child.is_file() and child.name not in ALLOWED_ROOT_FILES:
            _add(
                findings,
                "ROOT002",
                child.relative_to(root),
                "top-level file is not allowlisted",
            )


def validate_repository(root: Path = REPOSITORY_ROOT) -> list[Finding]:
    """Return every repository-contract violation under *root*."""

    root = root.resolve()
    findings: list[Finding] = []

    for required in sorted(REQUIRED_ROOT_FILES):
        if not (root / required).is_file():
            _add(findings, "ROOT003", required, "required governance file is missing")

    _validate_repository_paths(root, findings)

    for schema in ("schemas/lab.schema.json", "schemas/experiment.schema.json"):
        _load_json(root / schema, root, findings)

    labs_dir = root / "labs"
    if not labs_dir.is_dir():
        _add(findings, "ROOT004", "labs", "labs directory is missing")
    else:
        lab_count = 0
        experiment_count = 0
        for lab_dir in sorted(labs_dir.iterdir()):
            if not lab_dir.is_dir():
                continue
            lab_count += 1
            _, count = _validate_lab(lab_dir, root, findings)
            experiment_count += count
        if lab_count == 0:
            _add(findings, "ROOT005", "labs", "at least one lab is required")
        if experiment_count == 0:
            _add(
                findings,
                "ROOT006",
                "labs",
                "at least one experiment is required",
            )

    return sorted(set(findings))


def main(argv: Iterable[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if arguments:
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
