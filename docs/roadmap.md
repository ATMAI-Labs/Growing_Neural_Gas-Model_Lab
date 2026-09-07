# Research roadmap

The repository contains a canonical reference engine and two completed
synthetic experiments. Those establish a reproducible starting point. They do
not establish drift detection, semantic identity, explicit concept memory, or
a released ATMAI model.

## Current tranche

The next research question is tracked in
[issue #7](https://github.com/ATMAI-Labs/Growing_Neural_Gas-Model_Lab/issues/7):
does prior geometric exposure improve return-to-A performance when comparisons
share the same resource budget, training duration, and input samples?

Preparation adds a read-only reproduction command, a frozen evidence registry,
explicit reference-engine identity, status-aware evidence checks, and full
deterministic-result comparison in CI. Existing experiment bytes and the
canonical engine remain unchanged. Future engine changes require separate
versions and their own evidence, as described in [reproduction.md](reproduction.md).

The successor protocol is committed before its full 20-seed run. Its initial
scope is translation and recurrence; replicated rotation and density studies
remain separate follow-ups. A shared node cap is not automatically matched
realized capacity: any differences must be reported and limit interpretation.

## Gates

| Sequence | Work | Acceptance boundary |
| --- | --- | --- |
| 1 | Reproduction and evidence protection | Fresh runs compare all deterministic fields without altering retained files; completed experiments have checked execution, provenance, and evidence records. |
| 2 | Capacity-controlled replicated translation and recurrence | Paired seed results, stationary and history controls, explicit capacity accounting, uncertainty, and recovery onset and confirmation. Retain unfavorable and non-recovering runs. |
| 3 | Bounded-budget failure characterization | Demonstrate when dormant geometry helps recurrence or obstructs learning across multiple novel and recurring regimes. |
| 4 | One adaptation intervention at a time | Equal-budget comparison and ablations; measure update latency, model memory, representation error, and topology over node and dimension sweeps. |
| 5 | Delayed and missing labels | Explicit label-arrival timelines, no future-label leakage, and separate geometric and semantic metrics. |
| 6 | Explicit concept memory | Defined storage, matching, rejection and retrieval; false-recall measurements; repeatable benefit and bounded resources before promotion. |

## Engineering follow-ups

- Evaluate stricter integer parameter validation and overflow-safe state
  handling in a successor implementation; preserve the canonical reference.
- Add a documented installable reference package when reuse outside source
  checkouts is needed.
- Generate visual reports tying error, topology, graph capacity and dormant
  components to the same timeline.
- Measure scaling before optimizing nearest-node selection, adjacency lookup,
  per-step invariant checks or retained fit events.
- Keep GitHub code-owner review enforcement aligned with the charter's
  promotion requirement. The evidence registry and lab changes are routed to
  maintainers through CODEOWNERS.

No later gate is considered completed solely because its files or UI exist.
Follow the [research charter](research-charter.md) and open a scoped issue
before a new experiment or major implementation change.
