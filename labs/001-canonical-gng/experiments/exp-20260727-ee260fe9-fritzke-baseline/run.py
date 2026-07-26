"""Run the deterministic stationary-distribution GNG baseline.

The runner intentionally uses only Python's standard library.  With no
arguments it writes ``results/baseline.json`` beside this file; ``--stdout``
keeps smoke runs and automation free of result artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
import sys
import time
import tracemalloc
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Sequence, Tuple

from gng import GNGParameters, GrowingNeuralGas


Point = Tuple[float, float]
Sampler = Callable[[random.Random], Point]

EXPERIMENT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = EXPERIMENT_DIR / "results" / "baseline.json"
DEFAULT_STEPS = 10_000
DEFAULT_CHECKPOINTS = (0, 1_000, 5_000, 10_000)
EVALUATION_SAMPLE_COUNT = 2_048

# Each random role has an independent stream.  Adding evaluation samples, for
# example, therefore cannot perturb initialization or training.
SEEDS: Mapping[str, Mapping[str, int]] = {
    "uniform_square": {
        "initialization": 10_101,
        "training": 10_102,
        "evaluation": 10_103,
    },
    "noisy_ring": {
        "initialization": 20_101,
        "training": 20_102,
        "evaluation": 20_103,
    },
    "two_gaussian_blobs": {
        "initialization": 30_101,
        "training": 30_102,
        "evaluation": 30_103,
    },
    "two_moons": {
        "initialization": 40_101,
        "training": 40_102,
        "evaluation": 40_103,
    },
}

PROVENANCE_URLS = {
    "paper": (
        "https://proceedings.neurips.cc/paper/1994/hash/"
        "d56b9fc4b0f1be8871f5e1c40c0067e7-Abstract.html"
    ),
    "paper_pdf": (
        "https://proceedings.neurips.cc/paper/1994/file/"
        "d56b9fc4b0f1be8871f5e1c40c0067e7-Paper.pdf"
    ),
}

FIXTURE_DEFINITIONS = {
    "uniform_square": {
        "distribution": "x and y are independent Uniform(-1, 1)",
    },
    "noisy_ring": {
        "distribution": (
            "theta ~ Uniform(0, 2*pi), r = 1 + Normal(0, 0.05), "
            "point = (r*cos(theta), r*sin(theta))"
        ),
    },
    "two_gaussian_blobs": {
        "distribution": (
            "choose either component with probability 0.5; means are "
            "(-0.65, -0.35) and (0.65, 0.35), with independent "
            "Normal(0, 0.18) coordinate noise"
        ),
    },
    "two_moons": {
        "distribution": (
            "choose either moon with probability 0.5 and theta ~ Uniform(0, pi); "
            "base points are (cos(theta), sin(theta)) and "
            "(1-cos(theta), 0.5-sin(theta)); add independent Normal(0, 0.05) "
            "coordinate noise"
        ),
    },
}

METRIC_DEFINITIONS = {
    "mean_squared_quantization_error": (
        "arithmetic mean over the fixed evaluation fixture of the squared "
        "Euclidean distance from each sample to its nearest node"
    ),
    "topographic_error": (
        "fraction of the fixed evaluation fixture for which the nearest and "
        "second-nearest nodes do not share an edge"
    ),
    "components": "number of connected components in the final undirected graph",
    "isolates": "number of final nodes with degree zero",
    "churn": (
        "event counts after initialization: node insertions and removals, plus "
        "edge additions and removals reported by each online update; repeated "
        "changes to the same identity count as separate events"
    ),
    "timing_seconds": (
        "wall-clock elapsed time measured with time.perf_counter; training "
        "includes sample generation and online updates"
    ),
    "tracemalloc_peak_bytes": (
        "maximum Python-traced allocated memory during report construction; "
        "it excludes memory not tracked by tracemalloc"
    ),
}


def sample_uniform_square(rng: random.Random) -> Point:
    return (rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0))


def sample_noisy_ring(rng: random.Random) -> Point:
    theta = rng.uniform(0.0, math.tau)
    radius = 1.0 + rng.gauss(0.0, 0.05)
    return (radius * math.cos(theta), radius * math.sin(theta))


def sample_two_gaussian_blobs(rng: random.Random) -> Point:
    mean_x, mean_y = (
        (-0.65, -0.35) if rng.random() < 0.5 else (0.65, 0.35)
    )
    return (rng.gauss(mean_x, 0.18), rng.gauss(mean_y, 0.18))


def sample_two_moons(rng: random.Random) -> Point:
    theta = rng.uniform(0.0, math.pi)
    if rng.random() < 0.5:
        base_x, base_y = math.cos(theta), math.sin(theta)
    else:
        base_x, base_y = 1.0 - math.cos(theta), 0.5 - math.sin(theta)
    return (rng.gauss(base_x, 0.05), rng.gauss(base_y, 0.05))


SAMPLERS: Mapping[str, Sampler] = {
    "uniform_square": sample_uniform_square,
    "noisy_ring": sample_noisy_ring,
    "two_gaussian_blobs": sample_two_gaussian_blobs,
    "two_moons": sample_two_moons,
}


def _checkpoint_steps(training_steps: int) -> Tuple[int, ...]:
    """Keep canonical checkpoints and make a custom run end at its final step."""

    return tuple(
        sorted(
            {
                0,
                training_steps,
                *(
                    checkpoint
                    for checkpoint in DEFAULT_CHECKPOINTS
                    if checkpoint <= training_steps
                ),
            }
        )
    )


def _rounded(value: float) -> float:
    return round(value, 12)


def _evaluate(
    model: GrowingNeuralGas,
    evaluation_fixture: Sequence[Point],
    step: int,
) -> Dict[str, object]:
    return {
        "step": step,
        "mean_squared_quantization_error": _rounded(
            model.mean_squared_quantization_error(evaluation_fixture)
        ),
        "topographic_error": _rounded(
            model.topographic_error(evaluation_fixture)
        ),
        "nodes": len(model.node_vectors),
        "edges": len(model.edge_ages),
    }


def _run_dataset(
    name: str,
    sampler: Sampler,
    seeds: Mapping[str, int],
    parameters: GNGParameters,
    training_steps: int,
) -> Dict[str, object]:
    dataset_started = time.perf_counter()
    initialization_rng = random.Random(seeds["initialization"])
    training_rng = random.Random(seeds["training"])
    evaluation_rng = random.Random(seeds["evaluation"])

    initial_vectors = [sampler(initialization_rng) for _ in range(2)]
    evaluation_fixture = [
        sampler(evaluation_rng) for _ in range(EVALUATION_SAMPLE_COUNT)
    ]
    model = GrowingNeuralGas(initial_vectors, parameters)

    checkpoints = _checkpoint_steps(training_steps)
    checkpoint_set = set(checkpoints)
    checkpoint_metrics: List[Dict[str, object]] = []
    evaluation_seconds = 0.0

    evaluation_started = time.perf_counter()
    checkpoint_metrics.append(_evaluate(model, evaluation_fixture, 0))
    evaluation_seconds += time.perf_counter() - evaluation_started

    node_insertions = 0
    node_removals = 0
    edge_additions = 0
    edge_removals = 0
    training_seconds = 0.0

    for step in range(1, training_steps + 1):
        training_started = time.perf_counter()
        update = model.step(sampler(training_rng))
        training_seconds += time.perf_counter() - training_started

        node_insertions += int(update.inserted_node is not None)
        node_removals += len(update.removed_nodes)
        edge_additions += len(update.added_edges)
        edge_removals += len(update.removed_edges)

        if step in checkpoint_set:
            evaluation_started = time.perf_counter()
            checkpoint_metrics.append(
                _evaluate(model, evaluation_fixture, step)
            )
            evaluation_seconds += time.perf_counter() - evaluation_started

    components = model.connected_components()
    isolates = model.isolated_nodes()
    model.assert_invariants()
    total_seconds = time.perf_counter() - dataset_started

    return {
        "name": name,
        "seeds": dict(seeds),
        "initial_vectors": [
            [_rounded(coordinate) for coordinate in vector]
            for vector in initial_vectors
        ],
        "checkpoints": checkpoint_metrics,
        "final_graph": {
            "nodes": len(model.node_vectors),
            "edges": len(model.edge_ages),
            "components": len(components),
            "isolates": len(isolates),
        },
        "churn": {
            "node_insertions": node_insertions,
            "node_removals": node_removals,
            "edge_additions": edge_additions,
            "edge_removals": edge_removals,
            "node_events": node_insertions + node_removals,
            "edge_events": edge_additions + edge_removals,
        },
        "timing_seconds": {
            "training": _rounded(training_seconds),
            "evaluation": _rounded(evaluation_seconds),
            "total": _rounded(total_seconds),
        },
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_report(training_steps: int) -> Dict[str, object]:
    parameters = GNGParameters(max_nodes=100)
    source_files = {
        "gng.py": EXPERIMENT_DIR / "gng.py",
        "run.py": Path(__file__).resolve(),
    }

    tracemalloc.start()
    report_started = time.perf_counter()
    datasets = [
        _run_dataset(
            name=name,
            sampler=SAMPLERS[name],
            seeds=SEEDS[name],
            parameters=parameters,
            training_steps=training_steps,
        )
        for name in SAMPLERS
    ]
    report: Dict[str, object] = {
        "schema": "atmai.gng.stationary-baseline/v1",
        "experiment_id": "exp-20260727-ee260fe9",
        "provenance_urls": PROVENANCE_URLS,
        "definitions": {
            "fixtures": FIXTURE_DEFINITIONS,
            "metrics": METRIC_DEFINITIONS,
            "nearest_node_ties": (
                "equal-distance nodes are ordered by ascending integer node id"
            ),
            "parameter_profile": (
                "learning and aging values reproduce the cited paper's Figure "
                "2 example; max_nodes=100 is a local growth cap, and none of "
                "these values is claimed as a universal GNG default"
            ),
        },
        "seeds": SEEDS,
        "parameters": asdict(parameters),
        "protocol": {
            "training_steps_per_dataset": training_steps,
            "evaluation_checkpoints": list(_checkpoint_steps(training_steps)),
            "evaluation_samples_per_dataset": EVALUATION_SAMPLE_COUNT,
            "dimensions": 2,
            "dataset_order": list(SAMPLERS),
            "growth_cap_behavior": (
                "once 100 live nodes exist, insertion stops but all other "
                "online updates continue through the fixed training step count"
            ),
        },
        "environment": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "source_sha256": {
            name: _sha256(path) for name, path in source_files.items()
        },
        "datasets": datasets,
    }
    report["timing_seconds"] = {
        "total": _rounded(time.perf_counter() - report_started)
    }
    _, peak_bytes = tracemalloc.get_traced_memory()
    report["tracemalloc_peak_bytes"] = peak_bytes
    tracemalloc.stop()
    return report


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the deterministic canonical GNG stationary baseline."
    )
    parser.add_argument(
        "--steps",
        type=_non_negative_int,
        default=DEFAULT_STEPS,
        help=f"training updates per dataset (default: {DEFAULT_STEPS})",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="print compact JSON instead of writing results/baseline.json",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = json.dumps(
        build_report(args.steps),
        indent=2,
        sort_keys=True,
    )
    if args.stdout:
        sys.stdout.write(payload + "\n")
        return 0

    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(payload + "\n", encoding="utf-8")
    print(f"Wrote {DEFAULT_OUTPUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
