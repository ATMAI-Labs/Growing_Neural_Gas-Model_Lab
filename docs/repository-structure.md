# Repository structure

Folders organize work; they do not provide security. GitHub pull-request rules
and automated checks protect `main`.

## Labs

Labs use `labs/NNN-topic-slug/` and represent a stable research question.
People are listed in `lab.json`, not encoded in the folder name.

Labs are created rarely, after discussion in an issue.

## Experiments

Experiments use:

```text
exp-YYYYMMDD-8hex-short-slug/
├── experiment.json
└── README.md
```

The date and random token let contributors create experiments in parallel
without reserving a sequence number.

Create a new experiment for a new hypothesis. Do not rewrite a completed,
failed, or inconclusive experiment into a different claim.

## Stable source

Experiments may use code from `src/`. They must not import implementation code
from another experiment.

Move code into `src/` only in a dedicated pull request with tests, reproducible
evidence, provenance, and a clear explanation of what is now stable.

## Contributor access

New contributors begin with forks and pull requests. Trusted contributors may
later receive triage or write access, but nobody bypasses protected `main` or
merges failing checks.
