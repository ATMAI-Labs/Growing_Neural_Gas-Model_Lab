# Edge reset before return-A learning and topographic error

Status: **complete**. The preregistered five-pair panel has run. The retained
edges beat the cleared edges on the stated criterion in all five pairs, so the
hypothesis is **not supported**. The completed predecessor files and the canonical
engine are unchanged.

Tracking: [research issue 7](https://github.com/ATMAI-Labs/Growing_Neural_Gas-Model_Lab/issues/7).
Predecessor:
[`exp-20260907-8313df3e-capacity-controlled-recurrence`](../exp-20260907-8313df3e-capacity-controlled-recurrence/).

## Question and preregistered hypothesis

The completed successor found that prior-A history lowers return-A
quantization error (QE) in all 20 seeds while **raising** return-A topographic
error (TE) in all 20. This experiment asks one focused question about that
retained disadvantage:

> Does clearing the Hebbian edge set immediately before return-A learning reduce
> the prior-A arm's mean return-A topographic error relative to retaining those
> edges?

The primary estimand is the paired seed mean of

`mean return TE of the cleared arm - mean return TE of the retained arm`.

Negative values favour clearing. Squared quantization error, recovery, topology,
and capacity remain separate reported outcomes. There is no aggregate pass/fail
and no population claim.

## Reused data, hyperparameters, and seeds

Nothing about the data or the learning configuration is new. This runner imports
`src/atmai_gng/gng.py` only after requiring SHA-256
`e684e68c0e87a7664e7c5294647f3c09cdb939775e2d322321268b5c56d7ee10`, and it
imports no code from any other experiment.

- Seed IDs are exactly **0 through 4**, the first five of the successor's panel.
- Each stream uses `random.Random` with seed `202609070000 + 100 * seed_id +
  stream_id`; stream IDs 0 initialization, 1 warmup, 2 intervention, 3 return,
  4 heldout are unchanged, so every sample is the successor's own sample.
- Signals are isotropic Gaussian noise with per-axis standard deviation 0.35,
  translated to A = (0, 0) or B = (2.5, 1.5).
- Warmup is 10,000 A updates; the intervening B phase is 4,096 samples; the
  measured return-A phase is 4,096 samples in 16 non-overlapping 256-sample
  windows; the held-out reference is 2,048 points.
- `max_nodes` is the common 100-node cap. All other learning parameters are
  canonical defaults: insertion interval 100, winner rate 0.2, neighbour rate
  0.006, error reduction 0.5, max edge age 50, error decay 0.995.
- Every loss is scored **before** its update. Operational recovery thresholds are
  frozen from the pre-change warm-A held-out evaluation (1.25x QE; TE + 0.02
  capped at 1) and are shared by both arms.

## Paired design

Each seed builds one prior-A model: 10,000 warm-A updates, then the 4,096-sample
B intervention. At the end of that intervention the state is cloned twice. The
two clones are then compared for **exact, unrounded** full-state equality
(prototypes, node errors, edges and ages, next node ID, sample count, dimension,
parameters) before either takes a return sample. Both arms then consume the
identical return-A signal list, in the same order.

The only intended difference at the return boundary is the Hebbian edge set:

- **retained** — the clone as it stands.
- **cleared** — every entry of the edge-age map removed immediately before the
  first return-A sample.

The runner records, per seed, that nodes and node errors, `samples_seen`,
`next_node_id`, dimension, and parameters are all identical after the treatment,
that the treated state does differ, and that both arms scored every return
sample. Clearing edges is therefore the sole manipulated variable.

## Feasibility gate and the one recorded deviation

Clearing the edge set leaves **all 100 prototypes isolated**, which the
unchanged canonical engine forbids. Every seed therefore records a refusal
probe: a cleared copy of the boundary state is stepped with the unmodified
`GrowingNeuralGas`, which raises
`AssertionError: processed graphs must not contain isolated nodes`. In the
retained result this refusal occurs in all five seeds.

The cleared arm consequently runs on `EdgeClearGNG`, a subclass that replaces
`assert_invariants` and omits only the isolated-node clause. Every other canonical
invariant is repeated verbatim, no learning rule, parameter, insertion, or
pruning decision changes, and the report lists the overridden engine methods —
exactly `assert_invariants` — on every seed. The engine file itself is
unmodified.

That relaxation is sufficient only because the measured phase performs no
insertion: the prior-A arm already reached the 100-node cap during warmup, and
the cap is recorded as reached in all five seeds. This matters because the one
other canonical path that a neighborless graph would break is node insertion,
which requires the maximum-error node to have a neighbor. Recorded insertions
during the measured phase are **0** for both arms in all five seeds, so that
path was never reached. A unit test drives the same state into an insertion and
confirms the engine then refuses to continue and the seed is retained with its
failure record instead of being dropped.

The cleared arm is therefore a graph the canonical engine would never produce on
its own. That is reported with the measurement, not hidden behind it.

## Capacity and isolated-node verification

The question of whether isolated-node removal breaks the capacity match was part
of the preregistration, so it is measured rather than assumed:

| Check | Result across the five pairs |
| --- | --- |
| Nodes isolated at the return boundary, before the treatment | 0 |
| Nodes isolated immediately after the clear | 100 in every seed |
| Live-node counts, every preupdate sample and every postupdate state | matched exactly; 0 mismatched steps, no first mismatch |
| Nodes removed during the measured phase, cleared arm | 0 in every seed |
| Insertions during the measured phase, both arms | 0 in every seed |
| Minimum isolated prototypes held by the cleared arm | 10, 12, 10, 11, 11 |
| Sample at which the cleared graph first had no isolated prototype | never within 4,096 samples |

So isolated-node removal did **not** break the capacity match here, because no
removal occurred: the engine only deletes a prototype when one of its edges
expires, and a rebuilt graph keeps re-adjacent pairs alive. Capacity was already
capped, so nothing was inserted either. The cleared arm held a permanently
fragmented graph for the entire measured phase, which is the honest description
of the treatment rather than a matched-resource comparison.

## Observed results

Retained
[numeric report](results/edge-clear-return-topography.json) contains all five
seed outcomes, per-window metrics, capacity traces, refusal probes, recovery
measurements, and declared limits.

| Return-to-A measurement, mean over 5 pairs | Retained edges | Cleared edges |
| --- | ---: | ---: |
| Mean topographic error | 0.019238281250 | 0.061425781250 |
| Mean first-window topographic error | 0.043750000000 | 0.456250000000 |
| Mean squared quantization error | 0.006415716055 | 0.006536166568 |
| Final edge count (per seed) | 261, 250, 261, 248, 243 | 237, 217, 225, 222, 224 |
| Isolated prototypes at the end | 0, 0, 0, 0, 0 | 10, 12, 10, 11, 11 |

The primary paired mean return-TE difference is **+0.042187500000** with the
preregistered descriptive 95% seed-bootstrap interval
**[+0.040966796875, +0.043212890625]** from 10,000 resamples at RNG seed
202610099999. Positive favours **retaining** the edges. All five per-seed
differences are positive (0.043457031250, 0.041503906250, 0.040039062500,
0.043212890625, 0.042724609375). No seed is excluded, replaced, or re-run.

The cleared arm starts at TE 0.42 to 0.48 in its first window, where an emptied
edge set makes almost every nearest-two pair unconnected by construction. It
then decays steeply: by the last window its TE is 0.004 to 0.023, in the same
range as the retained arm's last window, and in two seeds it ends below the
retained arm's final window. It first falls below that reference in windows 7,
11, 15, 15, and never for the fifth seed, so most of the excess is transient
rebuild cost. The preregistered estimand is the whole-phase mean, and that mean
stays far higher for the cleared arm. Mean return QE is essentially unchanged
(+0.000120450513 in favour of retaining), so the reset buys no representation
error, and it delays joint recovery.

QE recovery confirmation is identical in both arms in every seed (1024, 768,
1536, 1024, 768 return samples). Joint QE/TE confirmation is **later** for the
cleared arm in four of five seeds (2304 vs 2048, 1280 vs 768, equal at 1536,
1792 vs 1024, 1280 vs 768). These are confirmations under operational
tolerances, not confidence bands.

The retained arm reproduces the completed successor's prior-A arm exactly for
these five seed IDs: identical intervention mean QE, return mean QE, return mean
TE, all 16 window means, held-out thresholds, and QE recovery decisions. That
equality is checked by a unit test against the frozen predecessor result, and it
is what makes the edge set the only manipulated variable.

## Reading of the result

The hypothesis is not supported, in the direction of harm. The successor's
prior-A topographic disadvantage is therefore not explained by stale B-era edges
that a reset could remove: at the moment A returns, the retained A-era adjacency
is net-useful, and a complete Hebbian reset discards both the B-era and the
A-era structure while the canonical rule can rebuild only part of it within
4,096 samples. Any future forgetting mechanism must respect the engine's
connectivity invariant — rewiring rather than deleting is the untested option,
not this deletion.

## Limitations

- Five paired seeds describe this fixed synthetic panel. They cannot support an
  inferential population claim, and the bootstrap interval is descriptive.
- The treatment is a **complete** edge reset, not a selective B-region reset, so
  it also removes valid A-region adjacency. A selective variant would test a
  weaker and more plausible claim.
- The cleared arm is not a canonical-engine graph: it holds 10 to 25 permanently
  isolated prototypes, a state the engine forbids. Its numbers describe a
  mechanism the engine refuses, and the isolated-node relaxation is a declared
  deviation, not a neutral refactor.
- Capacity was matched only in the sense that both arms held the same 100 nodes
  at every scored step. Edge counts, component structure, and topology are not
  matched resources, and the arms are deliberately not matched on them.
- Topographic error on synthetic Gaussian geometry says nothing about concept
  identity, delayed labels, real data, or a usable memory mechanism. No
  mechanism is proposed or promoted by this result.

## Commands

Preregistered panel, JSON on stdout, no retained file is written:

```bash
python3 labs/002-controlled-drift/experiments/exp-20261009-95f07e14-return-edge-clear-topography/run.py --stdout
```

The default worker count is `min(4, cpu_count)`; `--workers 1` runs
sequentially. Both were used here and produced identical deterministic output.
`--output /path/to/new-report.json` refuses existing files and any path under
`labs/` or `src/`. Freezing retained evidence is a separate reviewed action.

Reduced mechanics run, explicitly marked `configuration_kind: smoke`:

```bash
python3 labs/002-controlled-drift/experiments/exp-20261009-95f07e14-return-edge-clear-topography/run.py --seeds 0,1 --warmup-steps 600 --phase-steps 64 --window-size 16 --evaluation-points 64 --max-nodes 6 --bootstrap-resamples 100 --workers 1 --stdout
```

`fixtures/smoke.json` retains the result of exactly that reduced command. Its
test compares every field except `environment`. It is a mechanics check, not
evidence for the hypothesis.

Exact replay through the registry, which never modifies retained evidence:

```bash
python3 scripts/reproduce_experiments.py --experiment exp-20261009-95f07e14
```

Only `/environment` is excluded from that comparison. As with the completed
successor, last-decimal differences have been observed on other numerical
runtimes; the documented reference runtime is CPython 3.14.7 on macOS arm64. This
record was produced on CPython 3.14.8, macOS arm64.