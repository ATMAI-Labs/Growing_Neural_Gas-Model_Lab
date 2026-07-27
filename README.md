# ATMAI Growing Neural Gas Model Lab

_A project by ATMAI LABS_

[![Repository integrity](https://github.com/ATMAI-Labs/Growing_Neural_Gas-Model_Lab/actions/workflows/repository-integrity.yml/badge.svg)](https://github.com/ATMAI-Labs/Growing_Neural_Gas-Model_Lab/actions/workflows/repository-integrity.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An open research lab for understanding, benchmarking, and extending Growing
Neural Gas (GNG).

> **Status: pre-alpha.** The repository contains a research structure, not a
> released ATMAI model.

## What we are investigating

How can a GNG graph learn topology online, adapt to changing data streams, and
recover recurring concepts without confusing geometric similarity with semantic
identity?

The [research charter](docs/research-charter.md) explains the scientific
sequence. We begin by reproducing canonical GNG before adding drift or memory.

## Structure

Labs are organized by research question, not by person:

```text
labs/
├── 001-canonical-gng/
│   └── experiments/exp-20260727-ee260fe9-fritzke-baseline/
└── 002-controlled-drift/
    └── experiments/exp-20260727-eee720cf-frozen-baseline-drift/
src/
└── atmai_gng/
```

Authorship lives in the manifest and Git history. Folder names remain stable if
people join, leave, or collaborate.

Experimental work stays inside its experiment. Reusable code enters `src/` only
after it has tests and reproducible evidence.

## Contributing

1. For a new experiment or major change, open an issue first. Small fixes can
   start with a pull request.
2. Work in a fork or feature branch—never directly on `main`.
3. Add one focused experiment or change.
4. Run:

   ```bash
   python3 scripts/validate_repository.py
   python3 -m unittest discover -s tests -p 'test_*.py'
   ```

5. Open a draft pull request and merge only after the checks pass.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the short contribution guide.

## Public-repository boundaries

- Never commit secrets, private or clinical data, raw datasets, or model
  checkpoints.
- Record the source and license of code, papers, and datasets.
- Code without an explicit license may be studied but not copied.
- Label experiments as planned, running, complete, failed, or inconclusive.
- Do not present an exploratory result as an ATMAI capability.

## Current evidence

The canonical Fritzke baseline is reproduced in
[`labs/001-canonical-gng`](labs/001-canonical-gng/) and its unchanged reference
engine is promoted in [`src/atmai_gng`](src/atmai_gng/).

The first [controlled-drift diagnostic](labs/002-controlled-drift/) records
adaptation under translation, rotation, density reweighting, and A-B-A
recurrence. It also preserves the important negative boundary: low return
error coexisted with a dormant geometric component, and continuing node growth
confounded the recurrence comparison. No semantic memory claim is made.

## License

Repository software is available under the [MIT License](LICENSE). External
code, data, papers, and artifacts retain their own terms.
