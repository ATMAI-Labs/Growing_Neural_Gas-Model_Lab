"""Run the frozen canonical GNG against deterministic controlled drift.

Only Python's standard library is used.  Every input is scored before
``model.step`` so the reported window metrics are genuinely prequential.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple


EXPERIMENT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = EXPERIMENT_DIR.parents[3]
SOURCE_DIR = REPOSITORY_ROOT / "src"
GNG_SOURCE_PATH = SOURCE_DIR / "atmai_gng" / "gng.py"
EXPECTED_GNG_SHA256 = (
    "e684e68c0e87a7664e7c5294647f3c09cdb939775e2d322321268b5c56d7ee10"
)
GNG_SOURCE_SHA256 = hashlib.sha256(GNG_SOURCE_PATH.read_bytes()).hexdigest()
if GNG_SOURCE_SHA256 != EXPECTED_GNG_SHA256:
    raise ImportError(
        "stable GNG source does not match the preregistered Lab 001 snapshot "
        f"{EXPECTED_GNG_SHA256}"
    )
GNG_MODULE_NAME = "controlled_drift_pinned_gng"
GNG_SPEC = importlib.util.spec_from_file_location(GNG_MODULE_NAME, GNG_SOURCE_PATH)
if GNG_SPEC is None or GNG_SPEC.loader is None:
    raise ImportError(f"could not load pinned GNG module from {GNG_SOURCE_PATH}")
GNG_MODULE = importlib.util.module_from_spec(GNG_SPEC)
sys.modules[GNG_MODULE_NAME] = GNG_MODULE
GNG_SPEC.loader.exec_module(GNG_MODULE)

GNGParameters = GNG_MODULE.GNGParameters
GrowingNeuralGas = GNG_MODULE.GrowingNeuralGas
StepResult = GNG_MODULE.StepResult


Point = Tuple[float, float]
Sampler = Callable[[random.Random, int, int], Point]

SCHEMA = "atmai.gng.controlled-drift/v1"
EXPERIMENT_ID = "exp-20260727-eee720cf"
DEFAULT_STEPS_PER_PHASE = 4_096
DEFAULT_WINDOW_SIZE = 256
DEFAULT_OUTPUT = EXPERIMENT_DIR / "results" / "controlled-drift.json"
REFERENCE_MULTIPLIER = 1.25
RECOVERY_CONSECUTIVE_WINDOWS = 2

PROVENANCE_URLS = [
    "https://proceedings.neurips.cc/paper/1994/hash/"
    "d56b9fc4b0f1be8871f5e1c40c0067e7-Abstract.html",
    "https://doi.org/10.1007/BFb0020222",
    "https://doi.org/10.1016/j.neucom.2007.12.024",
    "https://doi.org/10.2307/2981683",
]

QE_KEY = "mean_squared_quantization_error_preupdate"
TE_KEY = "topographic_error_preupdate"

SEEDS: Mapping[str, Mapping[str, int]] = {
    "abrupt_translation": {
        "initialization": 11_001,
        "pre_change": 11_002,
        "post_change": 11_003,
    },
    "gradual_translation": {
        "initialization": 21_001,
        "pre_change": 21_002,
        "translation_ramp": 21_003,
        "target_hold": 21_004,
    },
    "abrupt_rotation_90": {
        "initialization": 31_001,
        "pre_change": 31_002,
        "post_change": 31_003,
    },
    "abrupt_mixture_reweighting": {
        "initialization": 41_001,
        "pre_change": 41_002,
        "post_change": 41_003,
    },
    "recurring_translation_aba": {
        "initialization": 51_001,
        "a_initial": 51_002,
        "b_shifted": 51_003,
        "a_return": 51_004,
    },
}

SCENARIO_DEFINITIONS: Mapping[str, Mapping[str, object]] = {
    "abrupt_translation": {
        "description": "Abrupt translation of an isotropic Gaussian input distribution.",
        "phase_order": ["pre_change", "post_change"],
        "transform": {
            "type": "translation",
            "from": [0.0, 0.0],
            "to": [2.5, 1.5],
        },
        "distribution": {
            "family": "Gaussian",
            "coordinate_standard_deviation": [0.35, 0.35],
        },
    },
    "gradual_translation": {
        "description": (
            "Linear translation ramp followed by a stationary target hold; "
            "endpoint recovery begins only after the ramp is complete."
        ),
        "phase_order": ["pre_change", "translation_ramp", "target_hold"],
        "transform": {
            "type": "linear_translation",
            "from": [0.0, 0.0],
            "to": [2.5, 1.5],
            "interpolation": "(sample_index + 1) / samples_in_ramp",
        },
        "distribution": {
            "family": "Gaussian",
            "coordinate_standard_deviation": [0.35, 0.35],
        },
    },
    "abrupt_rotation_90": {
        "description": (
            "Abrupt 90-degree counter-clockwise rotation of an anisotropic "
            "Gaussian input distribution about its zero mean."
        ),
        "phase_order": ["pre_change", "post_change"],
        "transform": {
            "type": "rotation",
            "angle_degrees_counter_clockwise": 90,
            "center": [0.0, 0.0],
        },
        "distribution": {
            "family": "anisotropic Gaussian",
            "principal_axis_standard_deviations": [0.9, 0.18],
        },
    },
    "abrupt_mixture_reweighting": {
        "description": (
            "Abrupt density reweighting of two fixed Gaussian components; "
            "component geometry does not change."
        ),
        "phase_order": ["pre_change", "post_change"],
        "transform": {
            "type": "mixture_weight_change",
            "from_weights": [0.8, 0.2],
            "to_weights": [0.2, 0.8],
        },
        "distribution": {
            "family": "two-component isotropic Gaussian mixture",
            "component_means": [[-1.25, 0.0], [1.25, 0.0]],
            "component_standard_deviation": 0.22,
        },
    },
    "recurring_translation_aba": {
        "description": "A-B-A recurrence of a translated Gaussian input distribution.",
        "phase_order": ["a_initial", "b_shifted", "a_return"],
        "transform": {
            "type": "recurring_translation",
            "a": [0.0, 0.0],
            "b": [2.5, 1.5],
            "sequence": ["A", "B", "A"],
        },
        "distribution": {
            "family": "Gaussian",
            "coordinate_standard_deviation": [0.35, 0.35],
        },
    },
}

METRIC_DEFINITIONS = {
    QE_KEY: (
        "Window mean of squared Euclidean distance to the nearest prototype, "
        "measured immediately before the sample updates the model."
    ),
    TE_KEY: (
        "Window fraction for which the two nearest pre-update prototypes do "
        "not share an edge."
    ),
    "churn": (
        "Counts of node insertion/removal and edge addition/removal events "
        "reported by model.step; repeated identity changes are separate events."
    ),
}


@dataclass(frozen=True)
class PhaseSpec:
    phase_id: str
    role: str
    sampler: Sampler


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    phases: Tuple[PhaseSpec, ...]
    reference_phase: str
    recovery_phase: str
    ramp_phase: Optional[str] = None
    recurrence: bool = False


def _rounded(value: float) -> float:
    return round(value, 12)


def _gaussian(
    rng: random.Random,
    center: Point = (0.0, 0.0),
    standard_deviation: Point = (0.35, 0.35),
) -> Point:
    return (
        rng.gauss(center[0], standard_deviation[0]),
        rng.gauss(center[1], standard_deviation[1]),
    )


def _translated(center: Point) -> Sampler:
    def sample(rng: random.Random, _index: int, _count: int) -> Point:
        return _gaussian(rng, center)

    return sample


def _translation_ramp(target: Point) -> Sampler:
    def sample(rng: random.Random, index: int, count: int) -> Point:
        progress = (index + 1) / count
        return _gaussian(rng, (target[0] * progress, target[1] * progress))

    return sample


def _anisotropic(rotated: bool) -> Sampler:
    def sample(rng: random.Random, _index: int, _count: int) -> Point:
        point = (rng.gauss(0.0, 0.9), rng.gauss(0.0, 0.18))
        return (-point[1], point[0]) if rotated else point

    return sample


def _mixture(weights: Tuple[float, float]) -> Sampler:
    def sample(rng: random.Random, _index: int, _count: int) -> Point:
        center_x = -1.25 if rng.random() < weights[0] else 1.25
        return (rng.gauss(center_x, 0.22), rng.gauss(0.0, 0.22))

    return sample


def build_scenarios() -> Tuple[ScenarioSpec, ...]:
    """Return the fixed scenario order and executable phase definitions."""

    origin = _translated((0.0, 0.0))
    shifted = _translated((2.5, 1.5))
    return (
        ScenarioSpec(
            "abrupt_translation",
            (
                PhaseSpec("pre_change", "reference", origin),
                PhaseSpec("post_change", "target", shifted),
            ),
            "pre_change",
            "post_change",
        ),
        ScenarioSpec(
            "gradual_translation",
            (
                PhaseSpec("pre_change", "reference", origin),
                PhaseSpec(
                    "translation_ramp",
                    "transition",
                    _translation_ramp((2.5, 1.5)),
                ),
                PhaseSpec("target_hold", "target", shifted),
            ),
            "pre_change",
            "target_hold",
            ramp_phase="translation_ramp",
        ),
        ScenarioSpec(
            "abrupt_rotation_90",
            (
                PhaseSpec("pre_change", "reference", _anisotropic(False)),
                PhaseSpec("post_change", "target", _anisotropic(True)),
            ),
            "pre_change",
            "post_change",
        ),
        ScenarioSpec(
            "abrupt_mixture_reweighting",
            (
                PhaseSpec("pre_change", "reference", _mixture((0.8, 0.2))),
                PhaseSpec("post_change", "target", _mixture((0.2, 0.8))),
            ),
            "pre_change",
            "post_change",
        ),
        ScenarioSpec(
            "recurring_translation_aba",
            (
                PhaseSpec("a_initial", "reference_a", origin),
                PhaseSpec("b_shifted", "intervening_b", shifted),
                PhaseSpec("a_return", "return_a", origin),
            ),
            "a_initial",
            "a_return",
            recurrence=True,
        ),
    )


def _squared_distance(left: Sequence[float], right: Sequence[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right))


def prequential_observation(
    model: GrowingNeuralGas, signal: Sequence[float]
) -> Dict[str, float]:
    """Measure one signal without mutating ``model``."""

    winner, runner_up = model.nearest_two(signal)
    vectors = model.node_vectors
    edge = (winner, runner_up) if winner < runner_up else (runner_up, winner)
    return {
        QE_KEY: _squared_distance(signal, vectors[winner]),
        TE_KEY: float(edge not in model.edge_ages),
    }


def _empty_churn() -> Dict[str, int]:
    return {
        "node_insertions": 0,
        "node_removals": 0,
        "edge_additions": 0,
        "edge_removals": 0,
    }


def _accumulate_churn(churn: Dict[str, int], update: StepResult) -> None:
    churn["node_insertions"] += int(update.inserted_node is not None)
    churn["node_removals"] += len(update.removed_nodes)
    churn["edge_additions"] += len(update.added_edges)
    churn["edge_removals"] += len(update.removed_edges)


def _with_totals(churn: Mapping[str, int]) -> Dict[str, int]:
    result = dict(churn)
    result["node_events"] = churn["node_insertions"] + churn["node_removals"]
    result["edge_events"] = churn["edge_additions"] + churn["edge_removals"]
    return result


def _graph_stats(model: GrowingNeuralGas) -> Dict[str, int]:
    return {
        "nodes": len(model.node_vectors),
        "edges": len(model.edge_ages),
        "components": len(model.connected_components()),
        "isolates": len(model.isolated_nodes()),
    }


def _component_summary(model: GrowingNeuralGas) -> List[Dict[str, object]]:
    vectors = model.node_vectors
    result = []
    for component in model.connected_components():
        centroid = [
            _rounded(
                sum(vectors[node_id][dimension] for node_id in component)
                / len(component)
            )
            for dimension in range(model.dimension)
        ]
        result.append(
            {
                "size": len(component),
                "centroid": centroid,
            }
        )
    return result


def recovery_delay(
    windows: Sequence[Mapping[str, object]],
    threshold: float,
    consecutive: int = RECOVERY_CONSECUTIVE_WINDOWS,
) -> Optional[int]:
    """Return samples to the first of consecutive QE windows within threshold.

    ``windows`` must already be restricted to the interval in which recovery
    is meaningful.  Delay is measured from the first supplied window's start
    to the recovered window's start.
    """

    if consecutive < 1:
        raise ValueError("consecutive must be positive")
    if not windows:
        return None
    start = int(windows[0]["start_step"])
    for index in range(len(windows) - consecutive + 1):
        candidate = windows[index : index + consecutive]
        if all(float(window[QE_KEY]) <= threshold for window in candidate):
            return int(windows[index]["start_step"]) - start
    return None


def _metric_recovery(
    windows: Sequence[Mapping[str, object]],
    metric: str,
    threshold: float,
    phase_start: int,
) -> Dict[str, object]:
    for index in range(len(windows) - RECOVERY_CONSECUTIVE_WINDOWS + 1):
        candidate = windows[index : index + RECOVERY_CONSECUTIVE_WINDOWS]
        if all(float(window[metric]) <= threshold for window in candidate):
            first = windows[index]
            second = candidate[-1]
            return {
                "recovered": True,
                "delay_samples": int(first["start_step"]) - phase_start,
                "first_window_index": first["window_index"],
                "first_window_start_step": first["start_step"],
                "confirmation_step": second["end_step"],
                "right_censored": False,
            }
    return {
        "recovered": False,
        "delay_samples": None,
        "first_window_index": None,
        "first_window_start_step": None,
        "confirmation_step": None,
        "right_censored": True,
    }


def _joint_recovery(
    windows: Sequence[Mapping[str, object]],
    thresholds: Mapping[str, float],
    phase_start: int,
) -> Dict[str, object]:
    for index in range(len(windows) - RECOVERY_CONSECUTIVE_WINDOWS + 1):
        candidate = windows[index : index + RECOVERY_CONSECUTIVE_WINDOWS]
        if all(
            float(window[metric]) <= threshold
            for window in candidate
            for metric, threshold in thresholds.items()
        ):
            first = windows[index]
            return {
                "recovered": True,
                "delay_samples": int(first["start_step"]) - phase_start,
                "first_window_index": first["window_index"],
                "first_window_start_step": first["start_step"],
                "confirmation_step": candidate[-1]["end_step"],
                "right_censored": False,
            }
    return {
        "recovered": False,
        "delay_samples": None,
        "first_window_index": None,
        "first_window_start_step": None,
        "confirmation_step": None,
        "right_censored": True,
    }


def _reference_band(
    windows: Sequence[Mapping[str, object]], reference_phase: str
) -> Dict[str, object]:
    source = [window for window in windows if window["phase"] == reference_phase][-1]
    metrics: Dict[str, Dict[str, float]] = {}
    for metric in (QE_KEY, TE_KEY):
        mean = float(source[metric])
        metrics[metric] = {
            "final_reference_window_mean": _rounded(mean),
            "lower_bound": 0.0,
            "upper_bound": _rounded(REFERENCE_MULTIPLIER * mean),
        }
    return {
        "method": "1.25 times the final pre-change window mean",
        "multiplier": REFERENCE_MULTIPLIER,
        "source_phase": reference_phase,
        "source_window_index": source["window_index"],
        "metrics": metrics,
    }


def _recovery_summary(
    windows: Sequence[Mapping[str, object]],
    recovery_phase: str,
    reference_band: Mapping[str, object],
) -> Dict[str, object]:
    candidates = [window for window in windows if window["phase"] == recovery_phase]
    phase_start = int(candidates[0]["start_step"])
    metric_bands = reference_band["metrics"]
    thresholds = {
        metric: float(metric_bands[metric]["upper_bound"])
        for metric in (QE_KEY, TE_KEY)
    }
    return {
        "phase": recovery_phase,
        "criterion": (
            "first of two consecutive windows at or below the reference "
            "upper bound; delay is to that first window's start"
        ),
        QE_KEY: _metric_recovery(
            candidates, QE_KEY, thresholds[QE_KEY], phase_start
        ),
        TE_KEY: _metric_recovery(
            candidates, TE_KEY, thresholds[TE_KEY], phase_start
        ),
        "joint": _joint_recovery(candidates, thresholds, phase_start),
    }


def _schedule(spec: ScenarioSpec, steps_per_phase: int) -> Dict[str, object]:
    phases = []
    for index, phase in enumerate(spec.phases):
        phases.append(
            {
                "phase": phase.phase_id,
                "role": phase.role,
                "start_step": index * steps_per_phase,
                "end_step": (index + 1) * steps_per_phase,
            }
        )
    return {
        "warmup_steps": steps_per_phase,
        "drift_start": steps_per_phase,
        "transition_steps": steps_per_phase if spec.ramp_phase else 0,
        "target_hold_steps": steps_per_phase,
        "return_start": 2 * steps_per_phase if spec.recurrence else None,
        "total_steps": len(spec.phases) * steps_per_phase,
        "phases": phases,
    }


def _run_scenario(
    spec: ScenarioSpec,
    parameters: GNGParameters,
    steps_per_phase: int,
    window_size: int,
) -> Dict[str, object]:
    seeds = SEEDS[spec.scenario_id]
    initialization_rng = random.Random(seeds["initialization"])
    first_sampler = spec.phases[0].sampler
    initial_vectors = [
        first_sampler(initialization_rng, index, steps_per_phase)
        for index in range(2)
    ]
    model = GrowingNeuralGas(initial_vectors, parameters)
    windows: List[Dict[str, object]] = []
    phases: List[Dict[str, object]] = []
    global_step = 0

    for phase in spec.phases:
        phase_rng = random.Random(seeds[phase.phase_id])
        phase_loss = 0.0
        phase_misses = 0.0
        phase_churn = _empty_churn()
        phase_graph_start = _graph_stats(model)
        first_window_index = len(windows)

        for window_offset in range(0, steps_per_phase, window_size):
            window_loss = 0.0
            window_misses = 0.0
            window_churn = _empty_churn()
            window_graph_start = _graph_stats(model)
            start_step = global_step

            for local_offset in range(window_size):
                phase_index = window_offset + local_offset
                signal = phase.sampler(phase_rng, phase_index, steps_per_phase)
                observation = prequential_observation(model, signal)
                window_loss += observation[QE_KEY]
                window_misses += observation[TE_KEY]
                update = model.step(signal)
                _accumulate_churn(window_churn, update)
                _accumulate_churn(phase_churn, update)
                global_step += 1

            graph_end = _graph_stats(model)
            windows.append(
                {
                    "window_index": len(windows),
                    "phase_window_index": window_offset // window_size,
                    "phase": phase.phase_id,
                    "start_step": start_step,
                    "end_step": global_step,
                    "sample_count": window_size,
                    QE_KEY: _rounded(window_loss / window_size),
                    TE_KEY: _rounded(window_misses / window_size),
                    "graph_start": window_graph_start,
                    **graph_end,
                    "churn": _with_totals(window_churn),
                }
            )
            phase_loss += window_loss
            phase_misses += window_misses

        phases.append(
            {
                "phase": phase.phase_id,
                "role": phase.role,
                "start_step": global_step - steps_per_phase,
                "end_step": global_step,
                "sample_count": steps_per_phase,
                "first_window_index": first_window_index,
                "last_window_index": len(windows) - 1,
                QE_KEY: _rounded(phase_loss / steps_per_phase),
                TE_KEY: _rounded(phase_misses / steps_per_phase),
                "graph_start": phase_graph_start,
                "graph_end": _graph_stats(model),
                "component_summary_end": _component_summary(model),
                "churn": _with_totals(phase_churn),
            }
        )

    model.assert_invariants()
    reference_band = _reference_band(windows, spec.reference_phase)
    recovery = _recovery_summary(windows, spec.recovery_phase, reference_band)
    result: Dict[str, object] = {
        "scenario_id": spec.scenario_id,
        "seeds": dict(seeds),
        "initial_vectors": [
            [_rounded(coordinate) for coordinate in vector]
            for vector in initial_vectors
        ],
        "schedule": _schedule(spec, steps_per_phase),
        "windows": windows,
        "phases": phases,
        "reference_band": reference_band,
        "recovery": recovery,
        "final_graph": _graph_stats(model),
        "final_component_summary": _component_summary(model),
    }

    if spec.ramp_phase:
        ramp = [window for window in windows if window["phase"] == spec.ramp_phase]
        upper = float(reference_band["metrics"][QE_KEY]["upper_bound"])
        denominator = max(upper, sys.float_info.epsilon)
        result["gradual_drift"] = {
            "endpoint_recovery_delay": recovery,
            "tracking_burden": {
                "ramp_phase": spec.ramp_phase,
                "windows_outside_reference_band": sum(
                    float(window[QE_KEY]) > upper for window in ramp
                ),
                "cumulative_normalized_excess": _rounded(
                    sum(
                        max(0.0, float(window[QE_KEY]) - upper) / denominator
                        for window in ramp
                    )
                ),
            },
        }

    if spec.recurrence:
        initial_a = [
            window for window in windows if window["phase"] == spec.reference_phase
        ]
        initial_start = int(initial_a[0]["start_step"])
        thresholds = {
            metric: float(reference_band["metrics"][metric]["upper_bound"])
            for metric in (QE_KEY, TE_KEY)
        }
        cold = {
            QE_KEY: _metric_recovery(
                initial_a, QE_KEY, thresholds[QE_KEY], initial_start
            ),
            TE_KEY: _metric_recovery(
                initial_a, TE_KEY, thresholds[TE_KEY], initial_start
            ),
            "joint": _joint_recovery(initial_a, thresholds, initial_start),
        }
        comparison: Dict[str, Dict[str, Optional[float]]] = {}
        for metric in (QE_KEY, TE_KEY, "joint"):
            cold_delay = cold[metric]["delay_samples"]
            return_delay = recovery[metric]["delay_samples"]
            comparison[metric] = {
                "cold_start_delay_samples": cold_delay,
                "return_a_delay_samples": return_delay,
                "delay_difference_samples": (
                    None
                    if cold_delay is None or return_delay is None
                    else return_delay - cold_delay
                ),
                "delay_ratio": (
                    None
                    if cold_delay in (None, 0) or return_delay is None
                    else _rounded(return_delay / cold_delay)
                ),
            }
        result["recurrence_comparison"] = {
            "reference": "final window of the initial A phase",
            "cold_start_convergence": cold,
            "return_a_recovery": recovery,
            "comparison": comparison,
        }
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _target_window_summary(
    scenario: Mapping[str, object], phase: str
) -> Dict[str, object]:
    windows = [
        window for window in scenario["windows"] if window["phase"] == phase
    ]
    values = [float(window[QE_KEY]) for window in windows]
    return {
        "phase": phase,
        "first_window": _rounded(values[0]),
        "peak_window": _rounded(max(values)),
        "late_window": _rounded(values[-1]),
        "window_count": len(values),
    }


def _hypothesis_evaluation(
    scenarios: Sequence[Mapping[str, object]],
) -> Dict[str, object]:
    by_id = {scenario["scenario_id"]: scenario for scenario in scenarios}
    clauses: List[Dict[str, object]] = []

    for scenario_id in (
        "abrupt_translation",
        "abrupt_rotation_90",
        "abrupt_mixture_reweighting",
    ):
        summary = _target_window_summary(by_id[scenario_id], "post_change")
        clauses.append(
            {
                "clause_id": f"{scenario_id}_late_below_first",
                "scenario_id": scenario_id,
                "comparison": "late_window < first_window",
                "first_window": summary["first_window"],
                "late_window": summary["late_window"],
                "passed": summary["late_window"] < summary["first_window"],
            }
        )

    abrupt_summary = _target_window_summary(
        by_id["abrupt_translation"], "post_change"
    )
    gradual_summary = _target_window_summary(
        by_id["gradual_translation"], "translation_ramp"
    )
    clauses.append(
        {
            "clause_id": "gradual_translation_peak_below_abrupt",
            "scenario_id": "gradual_translation",
            "comparison": "gradual_ramp_peak < abrupt_post_change_peak",
            "gradual_ramp_peak": gradual_summary["peak_window"],
            "abrupt_post_change_peak": abrupt_summary["peak_window"],
            "passed": (
                gradual_summary["peak_window"] < abrupt_summary["peak_window"]
            ),
        }
    )

    recurrence = by_id["recurring_translation_aba"]["recurrence_comparison"]
    recurrence_delays = recurrence["comparison"][QE_KEY]
    cold_delay = recurrence_delays["cold_start_delay_samples"]
    return_delay = recurrence_delays["return_a_delay_samples"]
    recurrence_passed = (
        None
        if cold_delay is None or return_delay is None
        else return_delay < cold_delay
    )
    recurrence_phases = {
        phase["phase"]: phase
        for phase in by_id["recurring_translation_aba"]["phases"]
    }
    clauses.append(
        {
            "clause_id": "recurring_translation_return_faster_than_cold_start",
            "scenario_id": "recurring_translation_aba",
            "comparison": "return_a_delay_samples < cold_start_delay_samples",
            "cold_start_delay_samples": cold_delay,
            "return_a_delay_samples": return_delay,
            "passed": recurrence_passed,
            "status": "inconclusive" if recurrence_passed is None else "scored",
            "capacity_context": {
                "cold_start_nodes": recurrence_phases["a_initial"]["graph_start"][
                    "nodes"
                ],
                "return_a_start_nodes": recurrence_phases["a_return"][
                    "graph_start"
                ]["nodes"],
            },
            "interpretation": (
                "This operational comparison does not isolate memory: the "
                "return phase starts with more prototypes and all residual "
                "graph state from A-B."
            ),
        }
    )

    return {
        "scored_independently": True,
        "aggregate_pass": None,
        "aggregate_note": (
            "No aggregate pass is defined; every preregistered clause remains "
            "an independent result."
        ),
        "clauses": clauses,
    }


def _validate_sizes(steps_per_phase: int, window_size: int) -> None:
    if steps_per_phase <= 0:
        raise ValueError("steps_per_phase must be positive")
    if window_size <= 0:
        raise ValueError("window_size must be positive")
    if steps_per_phase % window_size:
        raise ValueError("steps_per_phase must be a multiple of window_size")


def build_report(
    steps_per_phase: int = DEFAULT_STEPS_PER_PHASE,
    window_size: int = DEFAULT_WINDOW_SIZE,
) -> Dict[str, object]:
    """Build a deterministic, bounded controlled-drift evidence record."""

    _validate_sizes(steps_per_phase, window_size)
    parameters = GNGParameters()
    scenarios = build_scenarios()
    source_files = {
        "atmai_gng/gng.py": GNG_SOURCE_PATH,
        "run.py": Path(__file__).resolve(),
    }
    source_hashes = {
        name: _sha256(path) for name, path in source_files.items()
    }
    if source_hashes["atmai_gng/gng.py"] != EXPECTED_GNG_SHA256:
        raise RuntimeError(
            "stable GNG source does not match the preregistered Lab 001 "
            f"snapshot {EXPECTED_GNG_SHA256}"
        )
    scenario_results = [
        _run_scenario(
            scenario,
            parameters,
            steps_per_phase=steps_per_phase,
            window_size=window_size,
        )
        for scenario in scenarios
    ]
    return {
        "schema": SCHEMA,
        "experiment_id": EXPERIMENT_ID,
        "definitions": {
            "metrics": METRIC_DEFINITIONS,
            "scenarios": SCENARIO_DEFINITIONS,
            "window_boundaries": "start_step is inclusive; end_step is exclusive",
            "reference_and_recovery": (
                "Each metric upper bound is 1.25 times its final pre-change "
                "window mean. Recovery is the first of two consecutive target "
                "windows at or below that bound."
            ),
            "claim_boundaries": [
                "The streams alter only the input distribution P(X).",
                "No label, drift detector, reset, replay, or memory mechanism is used.",
                "Quantization error measures representation, not semantic identity.",
                (
                    "A faster A return can reflect greater node capacity or "
                    "residual prototypes and edges; it is not proof of memory."
                ),
                "This single-seed diagnostic does not estimate sampling uncertainty.",
                (
                    "Abrupt and gradual translation use independently seeded "
                    "streams, so their peak comparison is not paired."
                ),
            ],
        },
        "protocol": {
            "steps_per_phase": steps_per_phase,
            "window_size": window_size,
            "windows_are_non_overlapping": True,
            "measurement_order": "score signal, then call model.step(signal)",
            "scenario_order": [scenario.scenario_id for scenario in scenarios],
            "dimensions": 2,
            "reference_multiplier": REFERENCE_MULTIPLIER,
            "recovery_consecutive_windows": RECOVERY_CONSECUTIVE_WINDOWS,
            "expected_gng_sha256": EXPECTED_GNG_SHA256,
        },
        "seeds": {name: dict(values) for name, values in SEEDS.items()},
        "parameters": asdict(parameters),
        "environment": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "dependencies": "Python standard library plus repository src/atmai_gng",
        },
        "provenance_urls": PROVENANCE_URLS,
        "source_sha256": source_hashes,
        "hypothesis_evaluation": _hypothesis_evaluation(scenario_results),
        "scenarios": scenario_results,
    }


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the deterministic frozen-GNG controlled-drift baseline."
    )
    parser.add_argument(
        "--steps-per-phase",
        type=_positive_int,
        default=DEFAULT_STEPS_PER_PHASE,
        help=f"samples in each phase (default: {DEFAULT_STEPS_PER_PHASE})",
    )
    parser.add_argument(
        "--window-size",
        type=_positive_int,
        default=DEFAULT_WINDOW_SIZE,
        help=f"non-overlapping metric window size (default: {DEFAULT_WINDOW_SIZE})",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="print JSON instead of writing results/controlled-drift.json",
    )
    args = parser.parse_args(argv)
    if args.steps_per_phase % args.window_size:
        parser.error("--steps-per-phase must be a multiple of --window-size")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    payload = json.dumps(
        build_report(args.steps_per_phase, args.window_size),
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
