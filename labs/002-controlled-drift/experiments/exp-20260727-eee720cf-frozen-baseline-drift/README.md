# Experiment: Frozen canonical GNG baseline under controlled drift

## Status

Complete. The default 4,096-sample-per-phase run reproduced the preregistered
suite on 2026-07-27. Its machine-readable evidence is retained at
[`results/controlled-drift.json`](results/controlled-drift.json).

- Owner: [@abrahamabel](https://github.com/abrahamabel)
- Author: [@abrahamabel](https://github.com/abrahamabel)
- Entrypoint: [`run.py`](run.py)
- Proposal and scope: [GitHub issue #4](https://github.com/ATMAI-Labs/Growing_Neural_Gas-Model_Lab/issues/4)
- Predecessor: [`exp-20260727-ee260fe9-fritzke-baseline`](../../../001-canonical-gng/experiments/exp-20260727-ee260fe9-fritzke-baseline/)

## Research question

How does the promoted canonical GNG baseline respond prequentially to
controlled geometric and density drift, and which observed failures justify a
later adaptation or recurrence-memory mechanism?

## Hypothesis

With the canonical parameter profile unchanged, late-window prequential
squared quantization error will be lower than the first post-change window
after abrupt translation, 90-degree rotation, and mixture-density reweighting;
gradual translation will produce a lower peak rolling error than matched
abrupt translation; and A-B-A return will enter A's pre-change error band
faster than cold-start convergence. Each clause is scored separately and may
fail.

That preregistered wording is retained verbatim. In this first diagnostic,
“matched” means the gradual and abrupt fixtures share the same distribution
family and translation endpoints; their seeds and graph trajectories are
independent, so the peak comparison is unpaired. “Cold-start convergence”
means convergence within the recurrence scenario's initial A phase, not a
separate fresh-control run.

## Frozen baseline

The experiment imports the stable, dependency-free canonical implementation
from [`src/atmai_gng`](../../../../src/atmai_gng/). It does not copy or modify
the GNG engine inside the experiment.

The canonical Lab 001 parameter profile remains unchanged:
\(\lambda=100\), \(\epsilon_b=0.2\), \(\epsilon_n=0.006\),
\(\alpha=0.5\), \(a_{\max}=50\), global error decay \(d=0.995\), and a
100-node growth cap. The completed predecessor documents the update contract,
deterministic tie rules, and provenance. This experiment changes the incoming
stream, not the learning mechanism.

## Protocol

Only deterministic, repository-generated two-dimensional samples are used.
There are no external, personal, clinical, proprietary, or labeled data. Fixed
and independently recorded pseudo-random seeds govern every scenario.

The diagnostic suite evaluates these scenarios independently:

- abrupt translation;
- gradual translation endpoint-matched, but not seed-paired, to abrupt
  translation;
- abrupt 90-degree rotation of an anisotropic distribution;
- abrupt mixture-density reweighting; and
- A-B-A recurrence, compared with convergence during its initial A phase.

Every phase contains exactly 4,096 samples. Metrics are aggregated into 256
sample, non-overlapping windows, giving 16 complete windows per phase. Phase
boundaries, stream parameters, seeds, the GNG parameter profile, and the
100-node cap are recorded with the result.

For each incoming sample, the harness performs the following operations in
order:

1. Find the nearest and second-nearest prototypes in the current graph.
2. Record squared distance to the nearest prototype as the prequential
   quantization loss.
3. Record whether the two winning prototypes lack an edge as the prequential
   topographic miss.
4. Apply exactly one canonical online GNG update using that sample.

Measurement therefore precedes learning from the sample. There is no
look-ahead, held-out label, drift signal, or retrospective reassignment.

## Prespecified summaries and scoring

Window means are computed only from the fixed, consecutive 256-sample blocks.
The first post-change window is the immediate response, the largest applicable
post-change window mean is the peak response, and the final window of the
phase is the late response.

For each scenario, the pre-change reference threshold is fixed at \(1.25\)
times the mean squared quantization error in the final pre-change window. A
recovery is recorded only after two consecutive window means are at or below
that threshold; its delay begins at the relevant phase boundary and is
reported at the first of those two windows. If no qualifying pair occurs,
recovery is explicitly unresolved rather than inferred.

The hypothesis clauses are scored separately:

1. For abrupt translation, 90-degree rotation, and mixture-density
   reweighting, compare the late-window quantization error with the first
   post-change window.
2. Compare peak rolling quantization error under gradual translation with the
   endpoint-matched, independently seeded abrupt-translation peak.
3. Compare the A-B-A return's time to the A pre-change band with convergence
   during the same scenario's initial cold-start A phase.

The report also records topographic miss, node and edge counts, connected
components, isolates, graph churn, source hashes, and runtime-environment
metadata. These diagnostics contextualize quantization error but do not alter
the preregistered pass/fail comparisons.

## Reproduction

From the repository root:

```bash
PYTHONPATH=src python3 labs/002-controlled-drift/experiments/exp-20260727-eee720cf-frozen-baseline-drift/run.py
```

Repository-level validation remains:

```bash
python3 scripts/validate_repository.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

Do not mark the experiment complete or add a conclusion unless these commands
and the recorded experiment entrypoint succeed in the current worktree.

## Primary sources

- Bernd Fritzke, “A Growing Neural Gas Network Learns Topologies” (1994):
  [official record](https://proceedings.neurips.cc/paper/1994/hash/d56b9fc4b0f1be8871f5e1c40c0067e7-Abstract.html).
- Bernd Fritzke, work on GNG-U for non-stationary distributions (1997):
  [DOI 10.1007/BFb0020222](https://doi.org/10.1007/BFb0020222).
- Hervé Frezza-Buet, work on accuracy-controlled GNG-T (2008):
  [DOI 10.1016/j.neucom.2007.12.024](https://doi.org/10.1016/j.neucom.2007.12.024).
- A. Philip Dawid, the prequential evaluation principle (1984):
  [DOI 10.2307/2981683](https://doi.org/10.2307/2981683).

These sources motivate the baseline, non-stationary diagnostic context, and
measure-before-update evaluation order. Applying that order to label-free
quantization and topology losses is this experiment's protocol adaptation of
the prequential principle, not a claim that Dawid validated these particular
metrics. No third-party implementation code or external dataset is copied into
this experiment.

## Results

All five preregistered clauses passed their operational comparisons in this
single deterministic run:

| Clause | Prespecified comparison | Observed values | Score |
| --- | --- | --- | --- |
| Abrupt translation adapts | Late QE < first post-change QE | 0.013231 < 0.219780 | Pass |
| 90-degree rotation adapts | Late QE < first post-change QE | 0.011512 < 0.108273 | Pass |
| Mixture reweighting adapts | Late QE < first post-change QE | 0.005192 < 0.013218 | Pass |
| Gradual translation has a lower peak | Ramp peak QE < abrupt peak QE | 0.027831 < 0.219780 | Pass |
| A return is faster than initial A | Return delay < initial-phase cold-start delay | 0 < 3,072 samples | Pass |

QE recovery used the fixed 1.25-times-reference band and two-window
confirmation rule. Abrupt translation recovered in 2,560 samples, rotation in
1,536, density reweighting in 1,024, the fixed-target phase after gradual
translation in 512, and returning A in zero. Joint QE-and-topology recovery
was 2,560, 1,536, 2,304, 512, and zero samples, respectively.

The graph state prevents a stronger interpretation:

- Each drift begins after 4,096 samples, when the graph has 42 nodes. Abrupt
  target phases end with 83 nodes; the longer gradual and recurrence schedules
  reach the 100-node cap. Falling QE therefore combines online adaptation with
  continuing capacity growth.
- The A-B-A return starts with 83 nodes, whereas its initial cold-start A phase
  starts with two. Its zero-sample return score cannot isolate a memory effect.
- No node removals occurred in any scenario. At the end of B, the recurrence
  graph had a 39-node component near A and a 44-node component near B. After A
  returned, it still had two components: 55 nodes centered near
  \((-0.023, 0.016)\) and 45 centered near \((2.527, 1.490)\).
- Low return QE therefore coexists with a dormant geometric B component. This
  is inspectable residual topology, not evidence that the model recognized,
  named, or recalled a semantic concept.

The operational hypothesis is supported within this exact fixture and seed
policy. A causal comparison of adaptation or recurrence memory remains
inconclusive until a successor controls graph capacity, adds stationary
comparators, and repeats a preregistered seed panel.

The retained report binds the run to SHA-256
`532f75b9247ee36f5bd171386a81f6dee7d9e158d8b83a34726e317a4e5f6abc`
for `run.py` and
`e684e68c0e87a7664e7c5294647f3c09cdb939775e2d322321268b5c56d7ee10`
for the promoted canonical engine.

## Limitations

- Synthetic geometric drift is not semantic concept identity. Translation,
  rotation, or density reweighting cannot establish that a system recognizes
  the same or a different real-world concept.
- Faster A-B-A return may arise from residual graph topology rather than
  memory. It is not evidence of concept recall, episodic memory, or semantic
  persistence.
- The protocol has no labels and cannot establish classification accuracy,
  delayed-label behavior, or supervised drift performance.
- The experiment contains no drift detector and cannot measure detection
  quality, false alarms, or detection delay.
- No adaptive GNG variant or memory mechanism is tested, so the experiment
  cannot establish that such a mechanism improves the baseline.
- Controlled two-dimensional fixtures do not establish robustness,
  effectiveness, or readiness on real-world data.
- This first diagnostic uses one fixed seed set per scenario and does not
  estimate sampling uncertainty.
- The abrupt-versus-gradual peak comparison uses independently seeded streams;
  it is neither a paired-sample estimate nor a replicated effect size.
- Continued node growth confounds later-phase performance with increased
  capacity; the result is descriptive rather than a controlled causal estimate
  of adaptation speed.
