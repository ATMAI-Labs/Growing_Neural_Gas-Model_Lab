# ADR 0001: Organize labs by research question

- **Status:** Accepted
- **Date:** 2026-07-27

## Context

The repository needs to support multiple researchers and experiments without
allowing exploratory work to destabilize shared code. A proposed structure used
one lab folder per person.

## Decision

Use topic-based lab directories with stable numeric IDs. Use decentralized,
immutable experiment IDs made from a UTC date and random eight-character
hexadecimal token. Record people in manifests, pull requests, `CODEOWNERS`, and
Git history.

Use protected `main`, required pull requests, automated validation, and code
owner review as the actual repository safety boundary. Keep experimental code
inside its experiment until a separate evidence-backed promotion change moves
it into `src/`.

## Consequences

- Ownership can change without renaming scientific history.
- Automation can validate every lab with one contract.
- Parallel contributors can create experiments without reserving a sequence
  number.
- Experiments remain independently reviewable.
- Folder isolation does not replace access controls or review.
- Contributors must create a new experiment rather than silently rewriting a
  completed result.
