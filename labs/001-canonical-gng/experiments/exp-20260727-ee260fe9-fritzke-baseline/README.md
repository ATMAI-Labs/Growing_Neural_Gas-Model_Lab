# Experiment: Fritzke baseline

## Status

Complete. The default 10,000-step run reproduced all four fixtures on
2026-07-27, and its machine-readable report is retained at
[`results/baseline.json`](results/baseline.json).

- Owner: [@abrahamabel](https://github.com/abrahamabel)
- Author: [@abrahamabel](https://github.com/abrahamabel)
- Entrypoint: [`run.py`](run.py)

## Hypothesis

A direct, deterministic implementation of the canonical GNG update sequence
will reduce quantization error while learning a local prototype graph on
controlled two-dimensional stationary distributions.

## Canonical algorithm contract

The primary source is Bernd Fritzke, “A Growing Neural Gas Network Learns
Topologies,” *Advances in Neural Information Processing Systems 7*, pp. 625–632
([official record](https://proceedings.neurips.cc/paper/1994/hash/d56b9fc4b0f1be8871f5e1c40c0067e7-Abstract.html);
[paper PDF](https://papers.nips.cc/paper/1994/file/d56b9fc4b0f1be8871f5e1c40c0067e7-Paper.pdf)).
The paper first initializes two units at random positions. Its numbered update
order is then:

1. Draw one input signal from the distribution.
2. Find the nearest unit \(s_1\) and second-nearest unit \(s_2\).
3. Increment the age of every edge emanating from \(s_1\).
4. Add the squared distance from the signal to \(s_1\) to \(s_1\)'s local
   accumulated error.
5. Move \(s_1\) and its direct graph neighbors toward the signal by fractions
   \(\epsilon_b\) and \(\epsilon_n\), respectively.
6. Connect \(s_1\) and \(s_2\), creating the edge if absent or resetting its
   age to zero if present.
7. Remove edges whose age is greater than \(a_{\max}\), then remove any nodes
   left without an edge as a result.
8. Whenever the signal count is an integer multiple of \(\lambda\), find the
   maximum-error unit \(q\), then its maximum-error neighbor \(f\). Insert
   \(r\) halfway between them, replace edge \((q,f)\) with \((q,r)\) and
   \((r,f)\), multiply the errors of \(q\) and \(f\) by \(\alpha\), and give
   \(r\) the resulting error of \(q\).
9. Multiply every node's accumulated error by the global decay \(d\).
10. If the stopping criterion is not met, return to step 1.

This order matters. In particular, error is measured before adaptation,
neighbors are those present before the competitive edge is refreshed, pruning
precedes insertion, and global error decay is last.

## Parameter profile

The run uses the values printed for Fritzke's Figure 2 simulation. They are a
sourced experimental preset, not universal GNG defaults and not a claim of
optimality for the four fixtures.

| Paper symbol | Value | Meaning |
| --- | ---: | --- |
| \(\lambda\) | 100 | Insert a node every 100 input signals |
| \(\epsilon_b\) | 0.2 | Winner learning fraction |
| \(\epsilon_n\) | 0.006 | Direct-neighbor learning fraction |
| \(\alpha\) | 0.5 | Error multiplier for \(q\) and \(f\) at insertion |
| \(a_{\max}\) | 50 | Remove an edge only when its age is greater than 50 |
| \(d\) | 0.995 | Per-signal multiplier applied to every node error |

The experiment adds a 100-node growth cap so every fixture has the same bounded
graph size. Once the cap is reached, insertion stops but winner, neighbor,
edge-aging, pruning, and error-decay updates continue through 10,000 signals.
That behavior is a local protocol choice, not part of the Figure 2 parameter
list or the paper's stopping criterion.

## Deterministic implementation choices

Fritzke specifies the mathematical transitions but leaves a few machine-level
states and tie cases implicit. This implementation makes those inferences
explicit and tests them:

- The two initial nodes start with zero accumulated error.
- The initial edge set is empty; the first competitive Hebbian edge is created
  by step 6.
- The two initial vectors are sampled from the fixture distribution with a
  dedicated initialization seed. The original paper says only “random
  positions,” so this is an explicit protocol choice rather than a uniquely
  required interpretation.
- Every newly created or insertion edge starts at age zero.
- Node IDs are monotonically allocated integers. Equal-distance and equal-error
  ties resolve by the smaller stable node ID, including selection of \(s_1\),
  \(s_2\), \(q\), and \(f\).

These are reproducibility rules for this implementation, not claims that the
paper uniquely requires them. Separate fixed pseudo-random streams prevent
evaluation generation from perturbing initialization or training:

| Fixture | Initialization seed | Training seed | Evaluation seed |
| --- | ---: | ---: | ---: |
| Uniform square | 10,101 | 10,102 | 10,103 |
| Noisy ring | 20,101 | 20,102 | 20,103 |
| Gaussian blobs | 30,101 | 30,102 | 30,103 |
| Two moons | 40,101 | 40,102 | 40,103 |

The random fixtures and learned graph state are deterministic under this
protocol. Wall-clock and memory telemetry are environmental measurements and
are not expected to be byte-identical across hosts.

## Protocol

One-sample, label-free updates are run for 10,000 signals on each deterministic
two-dimensional fixture:

- uniform samples on \([-1,1]^2\);
- a noisy unit ring with radial noise \(\mathcal{N}(0,0.05)\);
- two equal isotropic Gaussian blobs centered at \((-0.65,-0.35)\) and
  \((0.65,0.35)\), each with standard deviation \(0.18\); and
- two equal interleaving moons with coordinate noise
  \(\mathcal{N}(0,0.05)\).

The harness uses a separate fixed evaluation set of 2,048 samples per fixture
and evaluates checkpoints at 0, 1,000, 5,000, and 10,000 updates. It records
the seeds, complete parameter profile, fixture definition, graph statistics,
metric values, and aggregate node/edge birth and removal counts. The
implementation and metrics are tested independently of any visualization.

## Reproduction

From this experiment directory:

```bash
python3 run.py
```

The command writes `results/baseline.json`. To print a report without writing
the result file:

```bash
python3 run.py --stdout
```

Repository-level validation remains:

```bash
python3 scripts/validate_repository.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

Run those two commands from the repository root.

## Metrics

- **Mean squared quantization error:** the arithmetic mean, over a fixed
  evaluation set, of the squared Euclidean distance from each sample to its
  nearest prototype. Lower is better for representation error; it says nothing
  by itself about graph topology.
- **Topographic error:** the fraction of evaluation samples whose nearest and
  second-nearest prototypes do not share an edge. Lower means those local
  winner pairs are more often represented by the learned graph.
- **Node and edge counts:** the number of live prototypes and undirected edges
  at a checkpoint.
- **Connected components and isolates:** the counts in the final graph,
  recorded descriptively. Connectivity is not an invariant or success
  requirement.
- **Churn:** aggregate counts over the run of node insertions/removals and edge
  creations/removals reported by online updates. Repeated changes to one
  identity count as separate events. Churn is not a quality score.
- **Timing:** wall-clock training, evaluation, and total seconds measured with
  `time.perf_counter`; values are host-dependent.
- **Peak traced memory:** the maximum Python allocation observed by
  `tracemalloc` while building the report. It excludes allocations that
  `tracemalloc` cannot see.

## Provenance and licensed behavioral comparisons

The implementation was written from the paper specification, independently of
third-party source code. No third-party source code was copied. The following
pinned repository snapshots were read only to compare observable update
behavior, parameter conventions, and edge-case choices (snapshots checked
2026-07-27):

| Reference snapshot | License | Use in this experiment |
| --- | --- | --- |
| [Smile `GrowingNeuralGas.java` at `8250509`](https://github.com/haifengl/smile/blob/825050961db43990f31355ea1234f6757a94a1b2/core/src/main/java/smile/vq/GrowingNeuralGas.java) | [GPL-3.0/commercial dual license](https://github.com/haifengl/smile/blob/825050961db43990f31355ea1234f6757a94a1b2/LICENSE) | GPL behavioral reference only; no code reuse |
| [dyconnmap `gng.py` at `cbef247`](https://github.com/makism/dyconnmap/blob/cbef247e635d55cb1489ba1e429d9d472b501b56/dyconnmap/cluster/gng.py) | [BSD-3-Clause](https://github.com/makism/dyconnmap/blob/cbef247e635d55cb1489ba1e429d9d472b501b56/LICENSE) | Behavioral comparison |
| [NeuPy `growing_neural_gas.py` at `317ed42`](https://github.com/itdxer/neupy/blob/317ed4204b5239e8be2b94a95fe3157c5f9edc65/neupy/algorithms/competitive/growing_neural_gas.py) | [MIT](https://github.com/itdxer/neupy/blob/317ed4204b5239e8be2b94a95fe3157c5f9edc65/LICENSE) | Behavioral comparison |
| [kudkudak `gng.R` at `c1c72fe`](https://github.com/kudkudak/Growing-Neural-Gas/blob/c1c72fe4f33cebe203f094babbe9b2bdddb85a02/R/gng.R) | [MIT](https://github.com/kudkudak/Growing-Neural-Gas/blob/c1c72fe4f33cebe203f094babbe9b2bdddb85a02/LICENSE) | Behavioral comparison |
| [Prosemble `growing_neural_gas.py` at `ea0caaf`](https://github.com/naotoo1/prosemble/blob/ea0caaf9a3bbedab93816c7a5c9c411d8cd41999/prosemble/models/growing_neural_gas.py) | [MIT](https://github.com/naotoo1/prosemble/blob/ea0caaf9a3bbedab93816c7a5c9c411d8cd41999/LICENSE) | Behavioral comparison |

These implementations differ in API, parameter semantics, update details, and
stopping rules. None is a semantic oracle for GNG; the paper-defined contract,
explicit local inferences, and tests govern this experiment.

## Results

The default command completed with the paper's Figure 2 parameter profile and
the fixed seeds above. The detailed checkpoints, churn, environment, timing,
memory measurement, and source hashes are preserved in
[`results/baseline.json`](results/baseline.json).

| Fixture | Seeds (init/train/eval) | Steps | Initial/final quantization error | Final topographic error | Nodes | Edges | Components |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Uniform square | 10,101 / 10,102 / 10,103 | 10,000 | 1.123948270770 → 0.007672573732 | 0.0185546875 | 100 | 246 | 1 |
| Noisy ring | 20,101 / 20,102 / 20,103 | 10,000 | 1.929937417533 → 0.002494494006 | 0.03515625 | 100 | 169 | 1 |
| Gaussian blobs | 30,101 / 30,102 / 30,103 | 10,000 | 0.887051192666 → 0.002836707424 | 0.0185546875 | 100 | 244 | 1 |
| Noisy moons | 40,101 / 40,102 / 40,103 | 10,000 | 0.551965514608 → 0.002536143283 | 0.01953125 | 100 | 168 | 2 |

All final graphs had zero isolated nodes. Quantization error fell on every
fixture, supporting the bounded hypothesis for these seeds and parameters.
Connectivity was not required: the two-moons graph finished with two
components.

The run also exposes a failure mode in treating prototype count or
quantization error as a proxy for topology. On the ring, topographic error was
0 at 1,000 and 5,000 steps but rose to 0.03515625 at 10,000 while quantization
error continued to fall. On two moons, topographic error rose from
0.00048828125 at 5,000 steps to 0.01953125 at 10,000 while quantization error
again fell. Under this profile, adding prototypes and lowering representation
error did not monotonically improve the learned topology.

## Limitations

- This is one parameter profile on stationary, synthetic, two-dimensional data;
  it does not establish general performance or parameter optimality.
- Graph connectivity is neither guaranteed nor required. Component count is a
  diagnostic, not a pass/fail condition.
- Quantization and topographic error measure geometric representation, not
  semantic identity, concept persistence, classification accuracy, or delayed
  label behavior.
- The 100-node cap and deterministic tie rules are experimental controls rather
  than universal parts of the original algorithm.
- Runtime and churn can vary with the execution environment or a materially
  changed protocol even when mathematical outputs remain reproducible.
- Cross-implementation comparison can reveal disagreements but cannot prove
  this implementation correct.

This experiment does not demonstrate concept drift handling, semantic memory,
classification, biological plausibility, or production readiness.
