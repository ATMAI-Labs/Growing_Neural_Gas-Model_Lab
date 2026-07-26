# Experiment: Fritzke baseline

## Status

Proposed. No implementation or result is present yet.

## Hypothesis

A direct, deterministic implementation of the canonical GNG update sequence
will reduce quantization error while learning a connected local prototype graph
on controlled two-dimensional stationary distributions.

## Planned protocol

1. Implement one-sample online updates without label input.
2. Exercise blobs, rings, two moons, and a uniform two-dimensional distribution.
3. Use fixed seeds and record every parameter.
4. Test graph invariants independently from visualization.
5. Record quantization error, topographic error, node count, edge count,
   connected components, and update time.

## Non-claims

This experiment will not demonstrate concept drift handling, semantic memory,
classification, biological plausibility, or production readiness.
