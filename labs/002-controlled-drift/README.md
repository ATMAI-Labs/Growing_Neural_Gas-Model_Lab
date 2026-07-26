# Lab 002: Controlled Drift

## Status and stewardship

- Status: Active
- Owner: [@abrahamabel](https://github.com/abrahamabel)
- Proposal and scope: [GitHub issue #4](https://github.com/ATMAI-Labs/Growing_Neural_Gas-Model_Lab/issues/4)

## Research question

How does the promoted canonical GNG baseline respond prequentially to
controlled geometric and density drift, and which observed failures justify a
later adaptation or recurrence-memory mechanism?

## Scope

This lab measures the unchanged canonical Growing Neural Gas implementation
from [`src/atmai_gng`](../../src/atmai_gng/) on deterministic, generated
two-dimensional streams. It isolates abrupt and gradual geometric change,
density reweighting, and recurrence while preserving the canonical parameter
profile and 100-node cap established by Lab 001.

Every loss is measured before the corresponding online update. This
prequential order exposes how the current graph handles each incoming sample
without look-ahead. Fixed phase boundaries and non-overlapping windows make
the immediate response, peak error, late error, and recovery delay directly
inspectable.

The lab is diagnostic. It does not introduce a drift detector, adaptive GNG
variant, labels, or a concept-memory mechanism. Any failure must be recorded
before a later experiment proposes a mechanism intended to address it.

## Experiments

| ID | Status | Purpose |
| --- | --- | --- |
| [`exp-20260727-eee720cf-frozen-baseline-drift`](experiments/exp-20260727-eee720cf-frozen-baseline-drift/) | Complete | Measure the frozen canonical baseline under controlled translation, rotation, density, and recurrence scenarios |

The first experiment is linked to its completed predecessor,
[`exp-20260727-ee260fe9-fritzke-baseline`](../001-canonical-gng/experiments/exp-20260727-ee260fe9-fritzke-baseline/).
The predecessor establishes stationary reference behavior; Lab 002 makes a new
claim in a new immutable experiment record.

## Exit criteria

- All streams are deterministic, synthetic-only, and fully described by
  recorded parameters and seeds.
- Quantization loss and topographic miss are measured before every update.
- Every phase contains 4,096 samples and every reported window contains 256
  consecutive, non-overlapping samples.
- The canonical parameter profile, 100-node cap, and stable
  `src/atmai_gng` implementation remain unchanged.
- Each clause of the preregistered hypothesis is scored separately, including
  failed or inconclusive clauses.
- Recovery uses the prespecified band and two-window rule, without changing the
  threshold after results are observed.
- The entrypoint records the protocol, metrics, source hashes, and runtime
  environment in a compact machine-readable result.
- Repository validation and tests pass before the experiment is marked
  complete.

## Interpretation boundary

The fixtures expose geometric representation under controlled change, not
semantic concept identity. Faster performance when a geometry returns may
reflect residual graph topology rather than memory. This lab cannot establish
delayed-label performance, real-world robustness, or the value of an adaptive
mechanism that it does not test.

The first experiment also exposed a protocol confound worth preserving: drift
begins while the canonical graph is still growing. Later phases therefore have
more prototypes than the initial cold-start phase. A successor that seeks a
causal adaptation or memory comparison must control capacity and repeat across
a preregistered seed panel rather than rewriting this completed record.
