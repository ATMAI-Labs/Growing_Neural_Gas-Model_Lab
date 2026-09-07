# Capacity-controlled replicated drift and recurrence

Status: **planned**. This document and runner define the protocol before the
full experiment. Reduced smoke runs validate mechanics and are not results of
the preregistered experiment. The protocol must be committed before running
the complete 20-seed panel. The completed predecessor files are unchanged.

Tracking: [research issue 7](https://github.com/ATMAI-Labs/Growing_Neural_Gas-Model_Lab/issues/7).

## Question and primary comparison

Does prior exposure to A improve return-A representation compared with a model
whose equally long history contains only B, under a common node cap? This tests
history-dependent geometric adaptation in canonical GNG. It does not introduce
an explicit memory, establish concept identity, detect drift, or evaluate labels.

The primary estimand is the paired seed mean of:

`mean return QE of abrupt A-history - mean return QE of B-only history`.

Negative values favor prior A exposure. Squared quantization error (QE) and
topographic error (TE) remain separate outcomes. There is no aggregate pass/fail.

## Frozen engine and fixed panel

The runner directly imports `src/atmai_gng/gng.py` after requiring SHA-256
`e684e68c0e87a7664e7c5294647f3c09cdb939775e2d322321268b5c56d7ee10`.
It imports no code from another experiment and changes no engine parameters
except the explicitly declared common `max_nodes=100` cap (also the current
canonical default). All learning rates, insertion frequency, and edge ageing
remain canonical defaults. The report records the engine and runner hashes.

Seed IDs are exactly **0 through 19**. Each stream uses Python `random.Random`
with seed `202609070000 + 100 * seed_id + stream_id`. Stream IDs are 0 for
initialization, 1 for warmup, 2 for intervention, 3 for return, and 4 for held-out
evaluation. No seed is dropped or replaced. Each stream is generated separately.

Signals are 2D isotropic Gaussian noise with standard deviation 0.35 per axis,
translated to A = (0, 0) or B = (2.5, 1.5). Warm-A and warm-B start from the same
two initialization noise points, translated to their respective centers, and
receive the same 10,000 warmup noise points under that translation.

Warmup is always 10,000 updates. If either model has fewer than 100 nodes at its
end, the seed is retained with a starting-capacity-failure flag; there is no
adaptive additional training. Counts alone do not establish equal state.

## Four paired arms

All arms run two phases of 4,096 updates after warmup:

| Arm | Warmup | Intervention | Return |
| --- | --- | --- | --- |
| `stationary` | A | A | A |
| `abrupt` | A | B | A |
| `gradual` | A | linear A to B | A |
| `b_only` | B | B | A |

The three A-history arms are deep copies of the same warm-A state. A full-state
digest includes prototypes, errors, edges and ages, next node ID, sample count,
dimension, and parameters. Exact unrounded full-state equality verifies copying
before intervention and confirms that held-out evaluation does not mutate it. The
B-only arm copies warm-B. Every arm receives the same base noise at each
corresponding phase step. All return signals are identical within a seed.

Gradual interpolation uses `i / (4096 - 1)` for step indices 0 through 4095,
including A and B endpoints with **no hold at B**. It therefore has less exact B
exposure and its return is a secondary exploratory history comparison. Its
intervention peak is compared descriptively with the abrupt arm's peak.

All arms have equal total update counts. Abrupt and B-only share the same
postwarmup B exposure, but their **total B exposure differs** because warmup
distribution is the treatment: abrupt has 4,096 B samples and B-only 14,096.
The report records exact A, exact B, and interpolated-center exposures explicitly.

## Measurements and capacity comparability

Score each sample **before updating**: squared distance to the nearest node for
QE; whether the nearest two nodes lack an edge for TE. Retain non-overlapping
256-sample window means, cumulative squared loss, phase means, node and edge
churn, component counts, and end-component centroids and sizes.

Record realized node counts at phase/window starts and ends, plus minimum and
maximum counts. Compare the primary pair's node counts for every scored sample
and every postupdate state. Keep exact mismatch counts and the first mismatch's
one-based sample index within its phase. Also report this check for the
abrupt/gradual comparison. A common cap is not evidence of equal realized
capacity. Any mismatch limits a capacity-isolated reading of the effect; all
such outcomes remain in the primary descriptive summary.

## Operational return bands

Evaluate warm-A on a separate 2,048-point A sample without adapting the model.
The same per-seed return thresholds apply to all arms, including stationary:

- QE threshold = 1.25 times warm-A held-out mean QE.
- TE threshold = minimum of 1 and warm-A held-out TE + 0.02.

These are operational tolerances, **not confidence bands**. QE recovery requires
two consecutive qualifying windows; joint recovery additionally requires the
TE criterion in both windows. Onset is the retrospective start of the first
window; confirmation is the end of the second. Thus zero-sample onset still
requires at least 512 return samples for confirmation. Unconfirmed arms have
null onset/confirmation and explicit right-censoring at 4,096 samples.

## Statistical summary and limits

Retain every seed-level outcome. Bootstrap the **20 paired seed-level mean
return-QE differences**, never windows or individual samples, using 10,000
resamples with independent RNG seed 202609079999. The descriptive 95% percentile
interval uses linear interpolation at `p * (n - 1)`. Report the paired TE
difference, stationary reference, all QE/joint confirmation and censoring
outcomes, and all capacity limitations alongside it. This fixed synthetic seed
panel does not support a confirmatory population claim.

The runner creates a deterministic report below 5 MiB, rounding floating
measurements to 12 decimal places after computation. Only `environment` contains
host/worker-dependent metadata. Process workers return results in seed order.
Data and model-state fingerprints hash canonical sorted-key JSON with the same
12-decimal normalization; source-file hashes remain byte-exact. Normalized
fingerprints describe the reported evidence and do not replace the exact
within-run state-equality checks. This normalization is fixed before the full run.

## Reproduction and smoke validation

After preregistration, the full command emits JSON on stdout without changing
any retained file:

```bash
python3 labs/002-controlled-drift/experiments/exp-20260907-8313df3e-capacity-controlled-recurrence/run.py --stdout
```

The default worker count is `min(4, cpu_count)`; `--workers 1` runs sequentially.
`--output /path/to/new-report.json` refuses existing files and all output under
`labs/` or `src/`. Freezing retained evidence is a separate reviewed action.

Reduced smoke run, explicitly marked `configuration_kind: smoke`:

```bash
python3 labs/002-controlled-drift/experiments/exp-20260907-8313df3e-capacity-controlled-recurrence/run.py --seeds 0,1 --warmup-steps 600 --phase-steps 64 --window-size 16 --evaluation-points 64 --max-nodes 6 --bootstrap-resamples 100 --workers 1
```

`fixtures/smoke.json` retains the result of exactly this reduced configuration
for a cross-platform mechanics check. Its test compares every field except
`environment`, including the runner hash, normalized state/data fingerprints,
and all numerical measurements. It is not evidence for the full-panel hypothesis.

Until the full panel has been run and reviewed, no result or research conclusion
is claimed for this experiment.

## Optional visual report

The numerical experiment uses only the Python standard library. To render an
existing JSON report as local HTML, install the optional plotting dependency in
a virtual environment and choose a new output outside completed experiments:

```bash
python3 -m venv /tmp/gng-report-venv
/tmp/gng-report-venv/bin/python -m pip install -r labs/002-controlled-drift/experiments/exp-20260907-8313df3e-capacity-controlled-recurrence/requirements-report.txt
/tmp/gng-report-venv/bin/python labs/002-controlled-drift/experiments/exp-20260907-8313df3e-capacity-controlled-recurrence/render_report.py /path/to/report.json --output /tmp/gng-report.html --png /tmp/gng-report.png
```

`--png` is optional. Both destinations must be new files. The renderer reports
the source JSON hash and summarizes its measurements without adding a new
statistical test. A visual report from smoke JSON remains smoke evidence.
