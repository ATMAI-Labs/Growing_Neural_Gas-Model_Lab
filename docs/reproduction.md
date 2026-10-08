# Reproduce the frozen GNG experiments

The launcher requires Python 3.10 or newer. Exact scientific replay also depends
on the numerical runtime; see the observed [portability boundary](portability.md).
From the repository root, run:

```bash
python3 scripts/reproduce_experiments.py
```

This command verifies every registered experiment. It checks the SHA-256 of
all registered engine and experiment files before executing each runner,
launches each runner with the current Python interpreter and `--stdout`, then
compares its complete deterministic JSON result with the retained artifact.
Bytecode writes are disabled for these subprocesses. The default command does
not create output files or modify the retained evidence. It verifies the frozen
files again after execution.

A mismatch prints the precise JSON pointer, expected value, and observed value.
Exit status is zero only if all selected experiments match and the frozen files
still match their hashes. Runner errors, invalid JSON, missing fields, changed
inputs, unknown experiment IDs, and deterministic differences return status one.
Floating-point values are compared exactly; there is no numerical tolerance.
JSON number types are also checked, and non-finite numbers are rejected.

To verify just one experiment:

```bash
python3 scripts/reproduce_experiments.py --experiment exp-20260727-eee720cf
```

Repeat `--experiment` to select several IDs. Frozen-file integrity is checked
for the entire registry even when only one experiment is selected.

To retain fresh output for inspection, select a directory outside the repository:

```bash
python3 scripts/reproduce_experiments.py --output-dir /tmp/gng-reproduction-20260907
```

Fresh files are named `<experiment-id>.json`. Existing files are never replaced;
choose a new directory for another run. The command rejects output directories
inside the repository, including paths that resolve there through symlinks.
Fresh output is retained even when its deterministic comparison fails so the
failure can be inspected. Such output does not replace or certify historical
results.

**Do not invoke the historical runners without `--stdout` for reproduction.**
Their original defaults write to their retained result paths. Those completed
experiment files remain unchanged; the repository command supplies their safe
mode explicitly.

## What varies between hosts

`reproducibility.json` enumerates the exact JSON pointers omitted from comparison.
For Lab 001 (`exp-20260727-ee260fe9`), they are:

- `/environment`
- `/timing_seconds`
- `/tracemalloc_peak_bytes`
- `/datasets/0/timing_seconds`
- `/datasets/1/timing_seconds`
- `/datasets/2/timing_seconds`
- `/datasets/3/timing_seconds`

For Lab 002 (`exp-20260727-eee720cf`), only `/environment` is omitted.
The capacity-controlled Lab 002 successor (`exp-20260907-8313df3e`) also omits
only `/environment`; every seed, metric, capacity gate and declared source/data
fingerprint is compared exactly. Its optional rendered report is a frozen
artifact; numerical replay does not require matplotlib or regenerate plots.
The edge-clear Lab 002 successor (`exp-20261009-95f07e14`) omits only
`/environment` as well; its paired-arm state equality checks, engine-deviation
record, refusal probes, capacity traces, and recovery decisions are all compared
exactly.

These fields describe the host, wall-clock time, and Python-traced allocation.
Each omitted field must still exist. All other values are checked, including
seeds, parameters, protocol, source hashes, definitions, every metric, dataset
order and array length, graph state, and hypothesis evaluations. A field named
`timing_seconds` elsewhere is not automatically excluded. Adding an exclusion
requires an explicit change to both the registry and the command's allowlist.

An exact mismatch on another Python version or architecture is a reproduction
failure requiring investigation. Do not add a tolerance merely to make it pass.
The runtime and hardware metadata remain available in freshly retained JSON.
The full successor panel has two observed last-decimal mismatches on Linux;
the documented CI reference is CPython 3.14.7 on macOS arm64. The exact comparison
rule and frozen scientific evidence are unchanged. See [portability.md](portability.md)
for the failure record, runtime scope, and remaining cross-platform work.

## Frozen references and future versions

The root registry uses schema `atmai.gng.reproducibility/v1`. It contains:

- `engines`: version identifiers mapped to repository-relative source paths and
  SHA-256 hashes. `canonical-gng-v1` currently identifies `src/atmai_gng/gng.py`.
- `experiments`: immutable experiment IDs, directories, entrypoints, retained
  result paths, engine identifiers, an explicit `files` map of every tracked
  file in each completed experiment and its SHA-256, and `ignore_json_paths`.

Paths must be canonical, relative, contained in the repository, and free of
symlink aliases. Manifest IDs, completion status, entrypoints, and retained
result IDs must agree with the registration. File coverage includes Git's tracked and visible untracked files so a new
registration can validate before staging and unregistered additions are caught.
A source archive without Git uses its non-bytecode file inventory.
The repository validator additionally requires every completed experiment to
have a registry entry.

The promoted `src/atmai_gng/gng.py` is an immutable reference for these registered
experiments. Lab 001 also retains its byte-identical local `gng.py`; both copies
are hashed. Lab 002 explicitly loads and checks the promoted reference. Do not
edit those files or refresh their registry hashes to justify a new claim.

An algorithm change belongs in a successor experiment with its own explicit
engine version, seeds, protocol, evidence, and predecessor links. Keep an
exploratory implementation within that new experiment until it satisfies the
repository's promotion requirements. A later promoted variant can use a new
module and a new registry engine identifier while the original reference stays
available. Alternatively, a future reproduction launcher can materialize the
original Git revision in a separate checkout; that workflow is not implemented
by this command.

The registry does not introduce a new algorithm version or repair the reference
engine's numerical limitations. It makes the existing evidence reproducible and
keeps later development from silently changing the historical baseline.

## Validation

```bash
python3 scripts/validate_repository.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/reproduce_experiments.py
```

The first two commands check repository integrity and focused behavior. The
third runs all registered scientific experiments and verifies their recorded
results. All three are useful, and a unit-test pass alone is not a full
experiment reproduction.
