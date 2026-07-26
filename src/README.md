# Stable source area

This directory is reserved for reusable implementation code promoted from
completed experiments.

## `atmai_gng`

`atmai_gng` is the dependency-free reference implementation of Fritzke's
canonical Growing Neural Gas update sequence. Its stable public interface is:

```python
from atmai_gng import GNGParameters, GrowingNeuralGas, StepResult
```

The repository does not yet publish an installable Python distribution. From a
source checkout, expose the package explicitly with `PYTHONPATH=src`, for
example:

```bash
PYTHONPATH=src python3 -c 'from atmai_gng import GrowingNeuralGas; print(GrowingNeuralGas)'
```

The implementation was promoted without modification from the completed
[`exp-20260727-ee260fe9-fritzke-baseline`](../labs/001-canonical-gng/experiments/exp-20260727-ee260fe9-fritzke-baseline/)
experiment. At promotion, both copies had SHA-256
`e684e68c0e87a7664e7c5294647f3c09cdb939775e2d322321268b5c56d7ee10`.
The frozen experiment retains the original reproducibility record and
provenance; conformance tests protect its snapshot and compare the promoted
engine against it step by step.

The implementation was independently written from Fritzke's 1994 paper. No
third-party implementation code was copied. It is distributed under the
repository's [MIT License](../LICENSE).

Promotion and future stable-source changes require the evidence, tests,
provenance, and review described in
[`docs/research-charter.md`](../docs/research-charter.md).
