# Research charter

## Purpose

This repository is a public, reproducible laboratory for understanding Growing
Neural Gas and for determining whether new mechanisms improve online topology
learning under non-stationarity.

It is not a product repository and it is not evidence that ATMAI has released a
working model.

## Guiding question

How can a Growing Neural Gas graph learn topology online, survive concept drift
and delayed labels, and recover recurring concepts without collapsing geometry
into class identity?

## Architectural boundaries

The research program tests four layers separately before testing their
interaction:

1. **Topology learner:** a label-free GNG graph of prototypes and competitive
   relationships.
2. **Drift adaptation:** mechanisms that move, insert, retire, or protect graph
   state as a distribution changes.
3. **Concept memory:** explicit storage, matching, uncertainty, and retrieval of
   prior regimes.
4. **Semantic association:** class or concept labels that may arrive late,
   sparsely, or never.

A change in geometry is not automatically a new semantic concept. Similar
geometry is not automatically proof that a previous semantic concept has
returned.

## Evaluation sequence

1. Replicate canonical GNG behavior on stationary synthetic distributions.
2. Measure adaptation under translation, rotation, density change, abrupt
   drift, and gradual drift.
3. Test recurrence with controlled `A → B → A` streams.
4. Add verification latency and missing-label conditions.
5. Compare explicit concept-memory mechanisms.
6. Formulate an ATMAI model only after baselines and failure modes are visible.

## Core measurements

- quantization error;
- topographic error;
- node and edge churn;
- connected components and isolated nodes;
- time and memory per update;
- drift adaptation delay;
- recurrence recovery delay;
- false concept recall;
- prequential predictive metrics only when labels are legitimately available.

## Evidence rules

- Primary papers and canonical publisher records support scientific claims.
- Other repositories are implementation references, not proof of correctness.
- AI-generated syntheses are maps to evidence, not primary evidence.
- Every numerical result records the code revision, environment, data
  provenance, parameters, seed policy, and evaluation window.
- Negative and inconclusive results remain part of the research record.

## Promotion criterion

Experimental work may enter `src/` only when it has:

- a stable specification;
- tests for algorithmic invariants;
- a reproducible experiment;
- benchmark evidence against the canonical baseline;
- documented provenance and licensing;
- maintainer and code-owner approval.
