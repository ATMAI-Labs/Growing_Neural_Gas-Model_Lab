# ATMAI Growing Neural Gas Model Lab

[![Repository integrity](https://github.com/ATMAI-Labs/Growing_Neural_Gas-Model_Lab/actions/workflows/repository-integrity.yml/badge.svg)](https://github.com/ATMAI-Labs/Growing_Neural_Gas-Model_Lab/actions/workflows/repository-integrity.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An open ATMAI research lab for studying, benchmarking, and extending Growing
Neural Gas (GNG) for online topology learning, non-stationary data streams, and
recurring concept memory.

> **Status: pre-alpha research scaffold.** No ATMAI model or performance claim
> has been released yet.

## Research question

How can a Growing Neural Gas graph learn topology online, survive concept drift
and delayed labels, and recover recurring concepts without collapsing geometry
into class identity?

The project deliberately separates four concerns:

1. **Geometry:** adaptive prototypes and their local graph topology.
2. **Adaptation:** how that topology follows a changing distribution.
3. **Concept memory:** how prior regimes are stored, matched, and recovered.
4. **Semantics:** how delayed or sparse labels are associated without rewriting
   geometric evidence.

See the [research charter](docs/research-charter.md) for the current hypotheses,
evidence boundaries, and evaluation sequence.

## Repository model

Labs are organized by a durable research question, not by a person's name.
Authorship and stewardship are recorded in each JSON manifest and in Git
history.

```text
labs/
└── 001-canonical-gng/
    ├── lab.json
    ├── README.md
    └── experiments/
        └── exp-20260727-ee260fe9-fritzke-baseline/
            ├── experiment.json
            └── README.md
```

A directory such as `Labs/Lab-1-Abe` would provide visual separation, but it
would not be a security boundary. GitHub rules, required pull requests, code
owner review, and automated validation protect the repository.

The stable areas have distinct roles:

| Path | Purpose |
| --- | --- |
| `labs/` | Isolated, reviewable research experiments |
| `src/` | Reusable code promoted from replicated experiments |
| `schemas/` | Machine-readable lab and experiment contracts |
| `templates/` | Starting points for new labs and experiments |
| `scripts/` | Repository-integrity tooling |
| `tests/` | Tests for repository tooling and promoted code |
| `docs/` | Research, governance, and architecture decisions |

Read [the repository structure contract](docs/repository-structure.md) before
creating a lab.

## Contribution flow

1. Open an experiment or research proposal issue.
2. Work in a fork or feature branch; never work directly on `main`.
3. Add one focused experiment with its manifest, hypothesis, provenance, and
   reproducibility notes.
4. Run:

   ```bash
   python3 scripts/validate_repository.py
   python3 -m unittest discover -s tests -p 'test_*.py'
   ```

5. Open a draft pull request.
6. Resolve review comments and pass the required repository-integrity check.
7. A maintainer squash-merges the approved pull request.

Start with [CONTRIBUTING.md](CONTRIBUTING.md). Governance and promotion rules
are in [GOVERNANCE.md](GOVERNANCE.md).

## Scientific safety

- Do not commit patient, clinical, confidential, or personally identifying
  data.
- Do not commit secrets, credentials, raw datasets, model checkpoints, or large
  generated artifacts.
- Record dataset sources, licenses, software provenance, parameters, seeds, and
  negative or inconclusive results.
- Do not describe an exploratory result as an ATMAI capability.
- Treat AI-generated research syntheses as navigation aids until their claims
  are verified against primary sources.

## Foundational reference

Bernd Fritzke, *A Growing Neural Gas Network Learns Topologies*, NeurIPS 1994.
The canonical baseline experiment is tracked in
[`labs/001-canonical-gng`](labs/001-canonical-gng/).

## License

Repository software is available under the [MIT License](LICENSE). Datasets,
third-party code, papers, figures, and model artifacts may have separate terms;
their provenance and licenses must be recorded before use.
