# Lab 001: Canonical Growing Neural Gas

## Research question

Can we reproduce the canonical Growing Neural Gas update rules and topology on
controlled stationary distributions with deterministic, inspectable behavior?

## Why this lab comes first

Any later claim about drift adaptation or concept memory needs a trustworthy
reference. This lab will establish the algorithm contract, invariants,
measurements, and failure cases of baseline GNG before extensions are added.

## Experiments

| ID | Status | Purpose |
| --- | --- | --- |
| [`exp-20260727-ee260fe9-fritzke-baseline`](experiments/exp-20260727-ee260fe9-fritzke-baseline/) | Proposed | Reproduce the canonical stationary-distribution baseline |

## Exit criteria

- The baseline update sequence is documented against the canonical paper.
- Deterministic synthetic examples learn non-empty prototype graphs.
- Tests cover insertion, winner/neighbor adaptation, edge aging, isolated-node
  removal, and error decay.
- Quantization and topographic metrics are recorded with seeds and parameters.
- At least one negative or failure-mode example is documented.
