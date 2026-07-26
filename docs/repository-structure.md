# Repository structure contract

## Why labs are not organized by person

Contributor folders such as `Lab-1-Abe` mix identity with scientific scope.
They become stale when ownership changes, encourage incompatible local
conventions, and make cross-experiment automation difficult. They also provide
no Git security boundary.

The durable unit is the research question:

```text
labs/NNN-lab-slug/
├── lab.json
├── README.md
└── experiments/
    └── exp-YYYYMMDD-8hex-experiment-slug/
        ├── experiment.json
        └── README.md
```

People are recorded in `owners` and `authors`, in pull requests, and in Git
history.

## Naming

- Lab IDs are three digits followed by a lowercase kebab-case slug. Labs are
  rare and receive their number in an accepted proposal issue.
- Experiment IDs contain their UTC creation date and a random eight-character
  lowercase hexadecimal token. This avoids central allocation and merge
  conflicts when contributors work in parallel.
- An experiment directory appends a lowercase kebab-case slug to the immutable
  experiment ID.
- IDs are never reused, even after an experiment is archived.
- Names describe the question or intervention, not the expected result.

Examples:

- `labs/001-canonical-gng`
- `labs/001-canonical-gng/experiments/exp-20260727-ee260fe9-fritzke-baseline`
- `labs/002-stream-drift/experiments/exp-20260803-a13f9c2d-abrupt-recurrence`

## Lab lifecycle

`proposed → active → completed → archived`

A completed lab remains available for provenance. Archiving is a status change,
not deletion.

## Experiment lifecycle

`proposed → active → completed`

An experiment may instead end as `inconclusive`, `failed`, or `archived`. Those
states are scientific outcomes, not repository failures.

## Isolation rules

- Experiments may depend on promoted code in `src/`.
- Experiments must not import implementation code from another experiment.
- A new hypothesis receives a new experiment directory.
- Raw datasets and generated model artifacts live outside Git. Manifests record
  stable source identifiers and checksums where possible.
- Small, reviewable plots and result summaries may be committed when their
  generation command and source experiment are documented.
- A pull request should normally touch one experiment or one shared concern.

## Ownership

Manifest owners are stewards and points of contact. GitHub `CODEOWNERS` controls
review routing. Only users with repository write access can be enforceable code
owners, so external contributors remain authors without receiving merge rights.

## Stable-code promotion

Code is copied or refactored into `src/` only through a dedicated promotion pull
request. That pull request must link the completed experiment, preserve
provenance, add tests, and explain which behavior is now considered stable.
