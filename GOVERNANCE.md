# Governance

## Principles

- `main` remains reviewable, reproducible, and green.
- Scientific history is preserved, including negative and inconclusive results.
- Repository permissions follow least privilege.
- Experimental evidence is not automatically a stable capability.
- Maintainers protect contributors as well as the codebase.

## Roles

### Contributors

Anyone may propose research, documentation, tests, or implementation changes
through issues and pull requests. Contributors do not receive merge rights by
default.

### Lab owners

Lab manifest owners steward a research question, coordinate experiments, and
review scientific scope. Manifest ownership is descriptive; it does not grant
GitHub permissions.

### Maintainers and code owners

The initial maintainers are `@abrahamabel` and `@akasaragod-kb`. They review
changes, maintain repository policy, manage releases and security reports, and
decide whether experimental work is promoted.

Maintainers must not approve their own pull requests. With two active
maintainers, one independent approval is required. Increase the required count
only after enough active maintainers exist to avoid deadlocking the repository.

## Change process

1. Discuss material research or architecture changes in an issue.
2. Submit a focused draft pull request.
3. Pass repository-integrity checks.
4. Receive code-owner approval from someone other than the latest contributor.
5. Resolve all review conversations.
6. Squash-merge to produce one revertable `main` commit per reviewed change.

Repository policy, workflows, schemas, stable source, and security files always
require code-owner review.

## Scientific lifecycle

Experiments advance through documented status changes:

`proposed → active → completed`

They may instead end as `inconclusive`, `failed`, or `archived`. Completed or
terminal experiments are not rewritten to support a different claim. A new
hypothesis creates a successor experiment with an explicit predecessor link.

## Promotion into stable source

Promotion into `src/` requires a dedicated pull request that:

- links a completed experiment;
- identifies which behavior is stable;
- adds algorithmic and regression tests;
- preserves code, data, and literature provenance;
- provides reproducible benchmark evidence;
- documents failure modes and limitations;
- receives independent maintainer approval.

Promotion is a reuse decision, not a declaration that every experimental claim
is true.

## Policy changes

Material changes to top-level structure, schemas, promotion rules, or security
controls require an architecture decision record under `docs/decisions/`.

Emergency security changes may be prepared privately through a GitHub security
advisory. The public record is added after disclosure is safe.
