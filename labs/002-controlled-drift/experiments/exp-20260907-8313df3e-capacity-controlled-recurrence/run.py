#!/usr/bin/env python3
"""Paired, replicated history comparison using the unchanged canonical engine.

The default command emits JSON on stdout. It never writes retained evidence.
Only dependency-free instrumentation is defined here; no other experiment is
imported. Reduced configurations are explicitly labelled smoke experiments.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
import platform
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[4]
ENGINE_PATH = ROOT / "src" / "atmai_gng" / "gng.py"
ENGINE_SHA256 = "e684e68c0e87a7664e7c5294647f3c09cdb939775e2d322321268b5c56d7ee10"
EXPERIMENT_ID = "exp-20260907-8313df3e"
SCHEMA = "atmai.gng.capacity-controlled-recurrence/v1"
SEED_IDS = tuple(range(20))
BOOTSTRAP_SEED = 202609079999
STREAM_IDS = {"initialization": 0, "warmup": 1, "intervention": 2, "return": 3, "heldout": 4}
ARMS = ("stationary", "abrupt", "gradual", "b_only")
A = (0.0, 0.0)
B = (2.5, 1.5)
SIGMA = 0.35
MAX_REPORT_BYTES = 5 * 1024 * 1024

if hashlib.sha256(ENGINE_PATH.read_bytes()).hexdigest() != ENGINE_SHA256:
    raise RuntimeError("canonical-gng-v1 source hash changed; this protocol requires its frozen engine")
_SPEC = importlib.util.spec_from_file_location("capacity_recurrence_canonical_gng", ENGINE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load the pinned canonical GNG engine")
ENGINE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ENGINE
_SPEC.loader.exec_module(ENGINE)
GNGParameters = ENGINE.GNGParameters
GrowingNeuralGas = ENGINE.GrowingNeuralGas


@dataclass(frozen=True)
class Configuration:
    seed_ids: tuple[int, ...] = SEED_IDS
    warmup_steps: int = 10000
    phase_steps: int = 4096
    window_size: int = 256
    evaluation_points: int = 2048
    max_nodes: int = 100
    bootstrap_resamples: int = 10000

    def __post_init__(self) -> None:
        if not self.seed_ids or any(type(seed) is not int or seed < 0 for seed in self.seed_ids):
            raise ValueError("seed ids must be non-negative integers and nonempty")
        if len(set(self.seed_ids)) != len(self.seed_ids):
            raise ValueError("seed ids must be unique; no seed may be counted twice")
        for name in ("warmup_steps", "phase_steps", "window_size", "evaluation_points", "max_nodes", "bootstrap_resamples"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_nodes < 2:
            raise ValueError("max_nodes must be at least two")
        if self.phase_steps % self.window_size or self.phase_steps < 2 * self.window_size:
            raise ValueError("each phase must contain at least two complete non-overlapping windows")


def stream_seed(seed_id: int, stream: str) -> int:
    return 202609070000 + 100 * seed_id + STREAM_IDS[stream]


def gaussian_noise(seed: int, count: int) -> list[tuple[float, float]]:
    rng = random.Random(seed)
    return [(rng.gauss(0.0, SIGMA), rng.gauss(0.0, SIGMA)) for _ in range(count)]


def translate(noise: Sequence[float], center: Sequence[float]) -> tuple[float, float]:
    return noise[0] + center[0], noise[1] + center[1]


def digest(value: Any) -> str:
    """Fingerprint the reported 12-decimal evidence representation."""

    return hashlib.sha256(json.dumps(round_report(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def full_state(model: Any) -> dict[str, Any]:
    """Capture all mutable engine state, including accumulated error and ages."""

    return {
        "parameters": asdict(model.parameters),
        "dimension": model.dimension,
        "samples_seen": model.samples_seen,
        "next_node_id": model._next_node_id,
        "nodes": [{"id": node_id, "vector": list(node.vector), "error": node.error}
                  for node_id, node in sorted(model._nodes.items())],
        "edges": [[left, right, age] for (left, right), age in sorted(model._edge_ages.items())],
    }


def state_summary(model: Any) -> dict[str, Any]:
    return {"sha256": digest(full_state(model)), "samples_seen": model.samples_seen,
            "node_count": len(model._nodes), "edge_count": len(model._edge_ages),
            "component_count": len(model.connected_components())}


def preupdate_errors(model: Any, signal: Sequence[float]) -> tuple[float, int]:
    # These pinned engine accessors are read-only; reusing the ranked distances
    # avoids another nearest-neighbour search for each of the two metrics.
    first, second, squared_distance, _ = model._nearest_two_with_distances(signal)
    missing_edge = int(model._edge(first, second) not in model._edge_ages)
    return squared_distance, missing_edge


def evaluate_reference(model: Any, points: Sequence[Sequence[float]]) -> dict[str, Any]:
    if not points:
        raise ValueError("held-out reference requires at least one point")
    before = full_state(model)
    measurements = [preupdate_errors(model, signal) for signal in points]
    qe = math.fsum(pair[0] for pair in measurements) / len(points)
    te = sum(pair[1] for pair in measurements) / len(points)
    if full_state(model) != before:
        raise AssertionError("held-out evaluation changed the starting model")
    return {"evaluation_points": len(points), "heldout_mean_qe": qe, "heldout_te": te,
            "qe_threshold": 1.25 * qe, "te_threshold": min(1.0, te + 0.02),
            "state_sha256_before_and_after": digest(before),
            "band_kind": "operational tolerances, not confidence bands"}


def empty_churn() -> dict[str, int]:
    return {"inserted_nodes": 0, "removed_nodes": 0, "added_edges": 0, "removed_edges": 0}


def add_churn(churn: dict[str, int], result: Any) -> None:
    churn["inserted_nodes"] += int(result.inserted_node is not None)
    churn["removed_nodes"] += len(result.removed_nodes)
    churn["added_edges"] += len(result.added_edges)
    churn["removed_edges"] += len(result.removed_edges)


def capacity_summary(counts: Sequence[int]) -> dict[str, int]:
    return {"start": counts[0], "end": counts[-1], "min": min(counts), "max": max(counts)}


def component_summary(model: Any) -> list[dict[str, Any]]:
    summaries = []
    for component in model.connected_components():
        vectors = [model._nodes[node_id].vector for node_id in component]
        centroid = [math.fsum(vector[axis] for vector in vectors) / len(vectors) for axis in range(2)]
        distance_a = math.dist(centroid, A)
        distance_b = math.dist(centroid, B)
        summaries.append({"node_count": len(component), "centroid": centroid,
                          "centroid_distance_to_a": distance_a, "centroid_distance_to_b": distance_b,
                          "nearest_center": "A" if distance_a <= distance_b else "B"})
    return summaries


def phase_signals(arm: str, phase: str, noise: Sequence[Sequence[float]]) -> list[tuple[float, float]]:
    if arm not in ARMS or phase not in {"intervention", "return"}:
        raise ValueError("unknown arm or phase")
    if phase == "return" or arm == "stationary":
        return [translate(point, A) for point in noise]
    if arm == "gradual":
        return [translate(point, (B[0] * index / (len(noise) - 1), B[1] * index / (len(noise) - 1)))
                for index, point in enumerate(noise)]
    return [translate(point, B) for point in noise]


def run_phase(model: Any, signals: Sequence[Sequence[float]], window_size: int, name: str) -> tuple[dict[str, Any], list[int]]:
    if not signals or len(signals) % window_size:
        raise ValueError("phase requires complete non-overlapping windows")
    windows = []
    counts = [len(model._nodes)]
    total_qe = 0.0
    total_misses = 0
    phase_churn = empty_churn()
    for window_start in range(0, len(signals), window_size):
        window_qe = []
        window_misses = 0
        window_churn = empty_churn()
        components_start = len(model.connected_components())
        for signal in signals[window_start:window_start + window_size]:
            qe, missing_edge = preupdate_errors(model, signal)
            window_qe.append(qe)
            window_misses += missing_edge
            result = model.step(signal)
            add_churn(window_churn, result)
            add_churn(phase_churn, result)
            counts.append(len(model._nodes))
        squared_loss = math.fsum(window_qe)
        total_qe += squared_loss
        total_misses += window_misses
        windows.append({"start_sample": window_start, "end_sample": window_start + window_size,
                        "mean_qe": squared_loss / window_size, "mean_te": window_misses / window_size,
                        "squared_loss": squared_loss, "topographic_misses": window_misses,
                        "cumulative_qe": total_qe,
                        "capacity": capacity_summary(counts[window_start:window_start + window_size + 1]),
                        "components_start": components_start, "components_end": len(model.connected_components()),
                        "churn": window_churn})
    return ({"name": name, "samples": len(signals), "mean_qe": total_qe / len(signals),
             "mean_te": total_misses / len(signals), "cumulative_qe": total_qe,
             "topographic_misses": total_misses, "capacity": capacity_summary(counts),
             "churn": phase_churn, "windows": windows,
             "start_training_count": model.samples_seen - len(signals), "end_training_count": model.samples_seen,
             "final_components": component_summary(model)}, counts)


def recovery(windows: Sequence[dict[str, Any]], qe_threshold: float, te_threshold: float | None = None) -> dict[str, Any]:
    streak = 0
    for index, window in enumerate(windows):
        qualifies = window["mean_qe"] <= qe_threshold and (te_threshold is None or window["mean_te"] <= te_threshold)
        streak = streak + 1 if qualifies else 0
        if streak == 2:
            return {"onset_samples": windows[index - 1]["start_sample"],
                    "confirmation_samples": window["end_sample"], "censored": False,
                    "horizon_samples": windows[-1]["end_sample"], "consecutive_windows": 2}
    return {"onset_samples": None, "confirmation_samples": None, "censored": True,
            "horizon_samples": windows[-1]["end_sample"] if windows else 0, "consecutive_windows": 2}


def compare_capacities(left: Sequence[int], right: Sequence[int]) -> dict[str, Any]:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("capacity traces must cover the same updates and include starting state")
    mismatches = [index + 1 for index, (a_count, b_count) in enumerate(zip(left[:-1], right[:-1])) if a_count != b_count]
    post_mismatches = [index + 1 for index, (a_count, b_count) in enumerate(zip(left[1:], right[1:])) if a_count != b_count]
    return {"compared_steps": len(left) - 1, "mismatched_steps": len(mismatches),
            "first_mismatch_step": mismatches[0] if mismatches else None,
            "postupdate_mismatched_steps": len(post_mismatches),
            "first_postupdate_mismatch_step": post_mismatches[0] if post_mismatches else None,
            "start_counts": [left[0], right[0]], "end_counts": [left[-1], right[-1]],
            "exactly_matched": not mismatches and not post_mismatches}


def exposure_record(arm: str, config: Configuration) -> dict[str, Any]:
    warm_a = 0 if arm == "b_only" else config.warmup_steps
    warm_b = config.warmup_steps if arm == "b_only" else 0
    phase_a = config.phase_steps if arm == "stationary" else int(arm == "gradual")
    phase_b = config.phase_steps if arm in {"abrupt", "b_only"} else int(arm == "gradual")
    return {"warmup": {"A": warm_a, "B": warm_b},
            "intervention": {"exact_A": phase_a, "exact_B": phase_b,
                             "interpolated_centers": config.phase_steps - phase_a - phase_b},
            "return": {"A": config.phase_steps, "B": 0},
            "total_exact_A_samples": warm_a + phase_a + config.phase_steps,
            "total_exact_B_samples": warm_b + phase_b,
            "total_training_updates": config.warmup_steps + 2 * config.phase_steps}


def run_seed(task: tuple[int, Configuration]) -> dict[str, Any]:
    seed_id, config = task
    seeds = {stream: stream_seed(seed_id, stream) for stream in STREAM_IDS}
    initialization = gaussian_noise(seeds["initialization"], 2)
    warmup_noise = gaussian_noise(seeds["warmup"], config.warmup_steps)
    intervention_noise = gaussian_noise(seeds["intervention"], config.phase_steps)
    return_noise = gaussian_noise(seeds["return"], config.phase_steps)
    heldout = gaussian_noise(seeds["heldout"], config.evaluation_points)
    params = GNGParameters(max_nodes=config.max_nodes)
    warm_a = GrowingNeuralGas([translate(point, A) for point in initialization], params)
    warm_b = GrowingNeuralGas([translate(point, B) for point in initialization], params)
    for point in warmup_noise:
        warm_a.step(translate(point, A))
        warm_b.step(translate(point, B))
    warmup = {"a": state_summary(warm_a), "b": state_summary(warm_b)}
    for state in warmup.values():
        state["reached_requested_capacity"] = state["node_count"] == config.max_nodes
    warmup["starting_capacity_failure"] = not all(warmup[history]["reached_requested_capacity"] for history in ("a", "b"))
    warmup["a_b_counts_equal"] = warmup["a"]["node_count"] == warmup["b"]["node_count"]
    reference = evaluate_reference(warm_a, heldout)
    arms = {}
    traces = {}
    for arm in ARMS:
        source = warm_b if arm == "b_only" else warm_a
        model = copy.deepcopy(source)
        starting_state = state_summary(model)
        if full_state(model) != full_state(source):
            raise AssertionError("arm cloning changed the full starting state")
        phases = []
        traces[arm] = {}
        for name, noise in (("intervention", intervention_noise), ("return", return_noise)):
            phase, trace = run_phase(model, phase_signals(arm, name, noise), config.window_size, name)
            if name == "return":
                phase["recovery"] = {"qe": recovery(phase["windows"], reference["qe_threshold"]),
                                     "joint": recovery(phase["windows"], reference["qe_threshold"], reference["te_threshold"])}
            phases.append(phase)
            traces[arm][name] = trace
        arms[arm] = {"starting_state": starting_state, "exposure": exposure_record(arm, config),
                     "phases": phases, "final_state": state_summary(model),
                     "final_components": component_summary(model)}
    primary_capacities = {name: compare_capacities(traces["abrupt"][name], traces["b_only"][name])
                          for name in ("intervention", "return")}
    secondary_capacities = {name: compare_capacities(traces["abrupt"][name], traces["gradual"][name])
                            for name in ("intervention", "return")}
    comparisons = {
        "primary_return_qe_difference": arms["abrupt"]["phases"][1]["mean_qe"] - arms["b_only"]["phases"][1]["mean_qe"],
        "primary_return_te_difference": arms["abrupt"]["phases"][1]["mean_te"] - arms["b_only"]["phases"][1]["mean_te"],
        "primary_capacity_by_phase": primary_capacities,
        "secondary_abrupt_gradual_capacity_by_phase": secondary_capacities,
        "abrupt_minus_gradual_peak_intervention_qe": max(window["mean_qe"] for window in arms["abrupt"]["phases"][0]["windows"]) - max(window["mean_qe"] for window in arms["gradual"]["phases"][0]["windows"]),
    }
    return {"seed_id": seed_id, "stream_seeds": seeds,
            "stream_sha256": {"initialization_base_noise": digest(initialization), "warmup_base_noise": digest(warmup_noise),
                              "intervention_base_noise": digest(intervention_noise), "shared_return_signals": digest(return_noise), "heldout_A": digest(heldout)},
            "warmup": warmup, "reference": reference, "arms": arms, "comparisons": comparisons,
            "capacity_limits_capacity_isolated_interpretation": warmup["starting_capacity_failure"] or not all(item["exactly_matched"] for item in primary_capacities.values())}


def quantile(values: Sequence[float], probability: float) -> float:
    if not values or not 0.0 <= probability <= 1.0:
        raise ValueError("quantile needs nonempty values and probability in [0, 1]")
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def paired_bootstrap(differences: Sequence[float], resamples: int, seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    if not differences or resamples < 1:
        raise ValueError("bootstrap requires paired seed outcomes and positive resamples")
    rng = random.Random(seed)
    n = len(differences)
    samples = [math.fsum(differences[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples)]
    return {"n": n, "mean_return_qe_difference": math.fsum(differences) / n,
            "ci95": [quantile(samples, 0.025), quantile(samples, 0.975)],
            "bootstrap_seed": seed, "bootstrap_resamples": resamples,
            "resampling_unit": "paired seed-level mean return loss difference",
            "quantile": "linear interpolation at p * (n - 1)",
            "interpretation": "descriptive percentile interval over this fixed synthetic seed panel"}


def summarize(outcomes: Sequence[dict[str, Any]], config: Configuration) -> dict[str, Any]:
    differences = [outcome["comparisons"]["primary_return_qe_difference"] for outcome in outcomes]
    primary = paired_bootstrap(differences, config.bootstrap_resamples)
    primary["seed_differences"] = [{"seed_id": outcome["seed_id"], "difference": difference} for outcome, difference in zip(outcomes, differences)]
    primary["capacity_mismatch_seed_ids"] = [outcome["seed_id"] for outcome in outcomes if not all(value["exactly_matched"] for value in outcome["comparisons"]["primary_capacity_by_phase"].values())]
    primary["warmup_capacity_failure_seed_ids"] = [outcome["seed_id"] for outcome in outcomes if outcome["warmup"]["starting_capacity_failure"]]
    return {"primary": primary,
            "mean_return_te_difference": math.fsum(outcome["comparisons"]["primary_return_te_difference"] for outcome in outcomes) / len(outcomes),
            "stationary_mean_return_qe": math.fsum(outcome["arms"]["stationary"]["phases"][1]["mean_qe"] for outcome in outcomes) / len(outcomes),
            "stationary_mean_return_te": math.fsum(outcome["arms"]["stationary"]["phases"][1]["mean_te"] for outcome in outcomes) / len(outcomes),
            "secondary_mean_abrupt_minus_gradual_peak_intervention_qe": math.fsum(outcome["comparisons"]["abrupt_minus_gradual_peak_intervention_qe"] for outcome in outcomes) / len(outcomes),
            "recovery_counts": {arm: {metric: {"confirmed": sum(not outcome["arms"][arm]["phases"][1]["recovery"][metric]["censored"] for outcome in outcomes),
                                               "censored": sum(outcome["arms"][arm]["phases"][1]["recovery"][metric]["censored"] for outcome in outcomes)}
                                      for metric in ("qe", "joint")} for arm in ARMS},
            "claim_limits": ["Geometry and graph continuity are measured; semantic identity, label handling, drift detection, and explicit memory are not evaluated.",
                             "Matched resource caps do not guarantee matched realized capacity. All mismatch and warmup-failure seeds are retained.",
                             "The primary comparison changes prior distribution exposure: total B exposure is greater in the B-only history control.",
                             "Gradual translation has no B hold and less exact B exposure. Its return is a secondary exploratory history comparison.",
                             "No aggregate pass/fail or confirmatory population claim is assigned."]}


def round_report(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("report contains a non-finite measurement")
        rounded = round(value, 12)
        return 0.0 if rounded == 0.0 else rounded
    if isinstance(value, dict):
        return {key: round_report(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [round_report(item) for item in value]
    return value


def build_report(config: Configuration = Configuration(), workers: int = 1) -> dict[str, Any]:
    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be a positive integer")
    tasks = [(seed, config) for seed in config.seed_ids]
    if workers == 1:
        outcomes = [run_seed(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            outcomes = list(executor.map(run_seed, tasks))
    report = {
        "schema": SCHEMA, "experiment_id": EXPERIMENT_ID,
        "configuration_kind": "preregistered" if config == Configuration() else "smoke",
        "configuration": asdict(config), "parameters": asdict(GNGParameters(max_nodes=config.max_nodes)),
        "protocol": {"seed_ids": list(config.seed_ids), "rng_seed_formula": "202609070000 + 100 * seed_id + stream_id",
                     "stream_ids": STREAM_IDS, "distribution": {"family": "isotropic Gaussian", "sigma": SIGMA, "A": A, "B": B},
                     "arm_order": ARMS, "phase_order": ["intervention", "return"],
                     "measurement": "squared quantization error and topographic missing-edge indicator before every update",
                     "capacity_comparison": "preupdate node count for every scored sample; first_mismatch_step is one-based within phase; also compare every postupdate count",
                     "thresholds": "independent warm-A heldout QE times 1.25 and min(1, warm-A heldout TE + 0.02), shared across all arms",
                     "recovery": "two consecutive non-overlapping windows; onset is retrospective first-window start; confirmation is second-window end",
                     "failure_policy": "retain every seed and capacity shortfall; no extra warmup, replacement, or seed exclusion",
                     "primary_estimand": "seed-mean return QE of abrupt A-history minus B-only history; negative favors prior A exposure",
                     "gradual_intervention": "center fraction i/(phase_steps-1), including A and B endpoints, with no B hold",
                     "fingerprint_normalization": "data and model-state fingerprints use canonical sorted-key JSON with floats rounded to 12 decimal places; source hashes remain byte-exact; within-run state checks use exact unrounded equality",
                     "rounding_decimal_places": 12},
        "provenance": {"engine_version": "canonical-gng-v1", "engine_path": ENGINE_PATH.relative_to(ROOT).as_posix(),
                       "engine_sha256": ENGINE_SHA256, "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       "predecessors": ["exp-20260727-ee260fe9", "exp-20260727-eee720cf"],
                       "issue": "https://github.com/ATMAI-Labs/Growing_Neural_Gas-Model_Lab/issues/7"},
        "environment": {"python": platform.python_version(), "implementation": platform.python_implementation(),
                        "platform": platform.platform(), "workers": workers},
        "seed_outcomes": outcomes, "summary": summarize(outcomes, config),
    }
    return round_report(report)


def encode_report(report: dict[str, Any]) -> str:
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if len(encoded.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("report exceeds the repository's 5 MiB artifact limit")
    return encoded


def write_new_output(path: Path, content: str) -> None:
    target = path.expanduser().resolve()
    if target.is_relative_to(ROOT / "labs") or target.is_relative_to(ROOT / "src"):
        raise ValueError("output must be outside labs/ and src/; retained evidence is frozen separately")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as output:
        output.write(content)


def parse_seed_ids(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(item.strip()) for item in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("seeds must be comma-separated integer IDs") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=parse_seed_ids, default=SEED_IDS)
    parser.add_argument("--warmup-steps", type=int, default=10000)
    parser.add_argument("--phase-steps", type=int, default=4096)
    parser.add_argument("--window-size", type=int, default=256)
    parser.add_argument("--evaluation-points", type=int, default=2048)
    parser.add_argument("--max-nodes", type=int, default=100)
    parser.add_argument("--bootstrap-resamples", type=int, default=10000)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--stdout", action="store_true", help="emit JSON on stdout (the default)")
    destination.add_argument("--output", type=Path, help="create a new output file outside labs/ and src/; refuse overwrite")
    args = parser.parse_args()
    try:
        config = Configuration(args.seeds, args.warmup_steps, args.phase_steps, args.window_size,
                               args.evaluation_points, args.max_nodes, args.bootstrap_resamples)
        if args.output is not None:
            destination_path = args.output.expanduser().resolve()
            if destination_path.exists() or destination_path.is_relative_to(ROOT / "labs") or destination_path.is_relative_to(ROOT / "src"):
                raise ValueError("output must be a new file outside labs/ and src/")
        encoded = encode_report(build_report(config, args.workers))
        if args.output is None:
            sys.stdout.write(encoded)
        else:
            write_new_output(args.output, encoded)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
