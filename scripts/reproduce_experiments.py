#!/usr/bin/env python3
"""Verify frozen experiments without changing retained evidence (stdlib only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "atmai.gng.reproducibility/v1"
ALLOWED_IGNORE_PATHS = frozenset({
    "/environment", "/timing_seconds", "/tracemalloc_peak_bytes",
    "/datasets/0/timing_seconds", "/datasets/1/timing_seconds",
    "/datasets/2/timing_seconds", "/datasets/3/timing_seconds",
})
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
EXPERIMENT_ID = re.compile(r"exp-[0-9]{8}-[0-9a-f]{8}\Z")


class ReproductionError(ValueError):
    """Invalid input or a failure to reproduce safely."""


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReproductionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ReproductionError(f"non-finite JSON value: {value}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ReproductionError(f"non-finite JSON number: {value}")
    return parsed


def _parse_json(text: str, label: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_object,
                          parse_constant=_invalid_constant, parse_float=_finite_float)
    except (ValueError, TypeError) as error:
        raise ReproductionError(f"{label}: invalid JSON: {error}") from error


def _read_json(path: Path) -> Any:
    try:
        return _parse_json(path.read_text(encoding="utf-8"), str(path))
    except (OSError, UnicodeError) as error:
        raise ReproductionError(f"cannot read {path}: {error}") from error


def _safe_path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ReproductionError(f"invalid relative path: {value!r}")
    parts = PurePosixPath(value).parts
    if (not parts or PurePosixPath(value).is_absolute() or any(p in {".", ".."} for p in parts)
            or PurePosixPath(value).as_posix() != value):
        raise ReproductionError(f"path must be canonical and relative: {value!r}")
    root = root.resolve()
    path = root.joinpath(*parts)
    try:
        path.resolve().relative_to(root)
    except (ValueError, RuntimeError) as error:
        raise ReproductionError(f"path escapes repository: {value!r}") from error
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ReproductionError(f"frozen paths cannot use symlinks: {value!r}")
    return path


def _require_fields(value: Any, fields: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise ReproductionError(f"{label}: expected exactly fields {sorted(fields)}")


def _require_hash(value: Any, label: str) -> None:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ReproductionError(f"{label}: expected lowercase SHA-256")


def _pointer_get(value: Any, pointer: str) -> Any:
    try:
        for component in pointer.split("/")[1:]:
            component = component.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                value = value[int(component)]
            elif isinstance(value, dict):
                value = value[component]
            else:
                raise KeyError(component)
        return value
    except (KeyError, IndexError, ValueError, TypeError) as error:
        raise ReproductionError(f"ignored path is missing: {pointer}") from error


def load_registry(root: Path, registry_path: Path | None = None) -> dict[str, Any]:
    """Validate registry schema, contained paths, and manifest/result identity.

    Hash verification is separate, so callers can report every changed file.
    Completed-experiment coverage is enforced by validate_repository.py.
    """
    root = root.resolve()
    registry = _read_json(registry_path or root / "reproducibility.json")
    _require_fields(registry, {"schema", "engines", "experiments"}, "registry")
    if registry["schema"] != SCHEMA:
        raise ReproductionError(f"registry schema must be {SCHEMA}")
    engines = registry["engines"]
    if not isinstance(engines, dict) or not engines:
        raise ReproductionError("engines must be a nonempty object")
    engine_paths: set[str] = set()
    for name, engine in engines.items():
        if not isinstance(name, str) or not name:
            raise ReproductionError("engine identifiers must be nonempty strings")
        _require_fields(engine, {"path", "sha256"}, f"engine {name}")
        _safe_path(root, engine["path"])
        if engine["path"] in engine_paths:
            raise ReproductionError(f"duplicate engine path: {engine['path']}")
        engine_paths.add(engine["path"])
        _require_hash(engine["sha256"], f"engine {name}")
    experiments = registry["experiments"]
    if not isinstance(experiments, list) or not experiments:
        raise ReproductionError("experiments must be a nonempty array")
    ids: set[str] = set()
    directories: set[str] = set()
    for experiment in experiments:
        _require_fields(experiment, {"id", "directory", "entrypoint", "result",
                                    "engine", "files", "ignore_json_paths"}, "experiment")
        identifier = experiment["id"]
        if not isinstance(identifier, str) or not EXPERIMENT_ID.fullmatch(identifier):
            raise ReproductionError("invalid experiment id")
        if identifier in ids:
            raise ReproductionError(f"duplicate experiment id: {identifier}")
        ids.add(identifier)
        directory = _safe_path(root, experiment["directory"])
        parts = directory.relative_to(root).parts
        if (len(parts) != 4 or parts[0] != "labs" or parts[2] != "experiments"
                or not parts[3].startswith(identifier + "-")):
            raise ReproductionError(f"{identifier}: invalid experiment directory")
        if experiment["directory"] in directories:
            raise ReproductionError(f"duplicate experiment directory: {directory}")
        directories.add(experiment["directory"])
        entrypoint = _safe_path(directory, experiment["entrypoint"])
        result = _safe_path(directory, experiment["result"])
        if not isinstance(experiment["engine"], str) or experiment["engine"] not in engines:
            raise ReproductionError(f"{identifier}: unknown engine")
        files = experiment["files"]
        if not isinstance(files, dict) or not files:
            raise ReproductionError(f"{identifier}: files must be a nonempty object")
        for relative, digest in files.items():
            path = _safe_path(root, relative)
            try:
                path.relative_to(directory)
            except ValueError as error:
                raise ReproductionError(f"{identifier}: frozen file outside experiment: {relative}") from error
            _require_hash(digest, relative)
        manifest_path = directory / "experiment.json"
        for path in (entrypoint, result, manifest_path):
            if path.relative_to(root).as_posix() not in files:
                raise ReproductionError(f"{identifier}: required frozen file missing: {path.name}")
        manifest = _read_json(manifest_path)
        if (not isinstance(manifest, dict) or manifest.get("id") != identifier
                or manifest.get("entrypoint") != experiment["entrypoint"]
                or manifest.get("status") != "complete"):
            raise ReproductionError(f"{identifier}: registry does not match completed manifest")
        expected = _read_json(result)
        if not isinstance(expected, dict) or expected.get("experiment_id") != identifier:
            raise ReproductionError(f"{identifier}: result experiment_id does not match")
        ignores = experiment["ignore_json_paths"]
        if (not isinstance(ignores, list) or any(not isinstance(p, str) for p in ignores)
                or len(set(ignores)) != len(ignores)
                or not set(ignores).issubset(ALLOWED_IGNORE_PATHS)):
            raise ReproductionError(f"{identifier}: invalid or unsupported ignore_json_paths")
        for pointer in ignores:
            _pointer_get(expected, pointer)
    return registry


def _experiment_files(root: Path, directory: str) -> set[str]:
    """Include tracked and visible untracked files; ignore generated caches."""
    if (root / ".git").exists():
        result = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "--others",
                                 "--exclude-standard", "-z", "--", directory],
                                capture_output=True, check=False)
        if result.returncode != 0:
            raise ReproductionError("cannot read experiment file inventory")
        return set(result.stdout.decode("utf-8").rstrip("\0").split("\0")) - {""}
    return {path.relative_to(root).as_posix() for path in (root / directory).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}}


def verify_frozen_files(root: Path, registry: dict[str, Any]) -> list[str]:
    """Return all hash/inventory failures; never execute experiment code."""
    root = root.resolve()
    failures: list[str] = []
    expected_files: dict[str, str] = {}
    for engine in registry["engines"].values():
        expected_files[engine["path"]] = engine["sha256"]
    for experiment in registry["experiments"]:
        files = experiment["files"]
        inventory = _experiment_files(root, experiment["directory"])
        for relative in sorted(inventory - set(files)):
            failures.append(f"unregistered experiment file: {relative}")
        for relative in sorted(set(files) - inventory):
            failures.append(f"frozen file absent from experiment inventory: {relative}")
        for relative, digest in files.items():
            if relative in expected_files and expected_files[relative] != digest:
                failures.append(f"conflicting frozen hashes: {relative}")
            expected_files[relative] = digest
    for relative, digest in sorted(expected_files.items()):
        try:
            path = _safe_path(root, relative)
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != digest:
                failures.append(f"SHA-256 mismatch {relative}: expected {digest}, got {actual}")
        except (OSError, ReproductionError) as error:
            failures.append(f"cannot verify {relative}: {error}")
    return failures


def compare_results(expected: Any, actual: Any, ignore_json_paths: Sequence[str]) -> list[str]:
    """Exact, type-sensitive comparison, ignoring only specified JSON pointers.

    An ignored field must still exist on both sides. There is no float tolerance,
    recursive name filtering, or filtering of array items.
    """
    if any(p not in ALLOWED_IGNORE_PATHS for p in ignore_json_paths):
        raise ReproductionError("unsupported ignored JSON path")
    failures: list[str] = []
    for pointer in ignore_json_paths:
        _pointer_get(expected, pointer)
        try:
            _pointer_get(actual, pointer)
        except ReproductionError as error:
            failures.append(str(error))
    ignored = set(ignore_json_paths)

    def descend(left: Any, right: Any, path: str) -> None:
        if path in ignored:
            return
        if type(left) is not type(right):
            failures.append(f"{path or '/'}: expected {type(left).__name__}, got {type(right).__name__}")
        elif isinstance(left, dict):
            for key in sorted(left.keys() | right.keys()):
                child = path + "/" + key.replace("~", "~0").replace("/", "~1")
                if key not in right:
                    failures.append(f"{child}: missing field")
                elif key not in left:
                    failures.append(f"{child}: unexpected field")
                else:
                    descend(left[key], right[key], child)
        elif isinstance(left, list):
            if len(left) != len(right):
                failures.append(f"{path}: expected {len(left)} items, got {len(right)}")
            for index, (a, b) in enumerate(zip(left, right)):
                descend(a, b, f"{path}/{index}")
        elif left != right:
            failures.append(f"{path or '/'}: expected {left!r}, got {right!r}")

    descend(expected, actual, "")
    return failures


def _output_paths(root: Path, output_dir: Path | None,
                  experiments: list[dict[str, Any]]) -> dict[str, Path]:
    if output_dir is None:
        return {}
    destination = output_dir.expanduser().resolve()
    try:
        destination.relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise ReproductionError("--output-dir must be outside the repository, including symlinks")
    paths = {item["id"]: destination / (item["id"] + ".json") for item in experiments}
    for path in paths.values():
        if path.exists() or path.is_symlink():
            raise ReproductionError(f"refusing to overwrite existing output: {path}")
    if destination.exists() and not destination.is_dir():
        raise ReproductionError(f"output destination is not a directory: {destination}")
    return paths


def main(argv: Sequence[str] | None = None, *, root: Path = REPOSITORY_ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", action="append", default=[], metavar="ID",
                        help="verify this registered experiment (repeatable; default: all)")
    parser.add_argument("--output-dir", type=Path,
                        help="retain fresh JSON outside the repository; existing files are never replaced")
    args = parser.parse_args(argv)
    try:
        registry = load_registry(root)
        failures = verify_frozen_files(root, registry)
        if failures:
            raise ReproductionError("frozen input verification failed:\n" + "\n".join(failures))
        registered = {item["id"]: item for item in registry["experiments"]}
        unknown = set(args.experiment) - registered.keys()
        if unknown:
            raise ReproductionError(f"unregistered experiments: {', '.join(sorted(unknown))}")
        experiments = [item for item in registry["experiments"]
                       if not args.experiment or item["id"] in args.experiment]
        outputs = _output_paths(root, args.output_dir, experiments)
        has_mismatch = False
        for experiment in experiments:
            identifier = experiment["id"]
            directory = _safe_path(root, experiment["directory"])
            runner = _safe_path(directory, experiment["entrypoint"])
            print(f"Running {identifier} (frozen files verified)...", flush=True)
            completed = subprocess.run([sys.executable, "-B", str(runner), "--stdout"],
                                       cwd=root, text=True, capture_output=True, check=False)
            if completed.returncode != 0:
                raise ReproductionError(f"{identifier}: runner exited {completed.returncode}\n{completed.stderr}")
            actual = _parse_json(completed.stdout, identifier)
            expected = _read_json(_safe_path(directory, experiment["result"]))
            differences = compare_results(expected, actual, experiment["ignore_json_paths"])
            if outputs:
                path = outputs[identifier]
                # Recheck resolved destination immediately before exclusive creation.
                _output_paths(root, path.parent, [experiment])
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("x", encoding="utf-8") as handle:
                    handle.write(completed.stdout)
                print(f"Fresh result: {path}")
            if differences:
                has_mismatch = True
                print(f"FAIL {identifier}: {len(differences)} deterministic difference(s)")
                for difference in differences:
                    print(f"  {difference}")
            else:
                print(f"PASS {identifier}: exact deterministic match; ignored only "
                      + ", ".join(experiment["ignore_json_paths"]))
        # Catch input changes during execution as well as before it.
        failures = verify_frozen_files(root, registry)
        if failures:
            raise ReproductionError("frozen inputs changed during reproduction:\n" + "\n".join(failures))
        return 1 if has_mismatch else 0
    except (ReproductionError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
