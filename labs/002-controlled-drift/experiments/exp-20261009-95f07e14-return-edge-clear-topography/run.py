#!/usr/bin/env python3
"""Paired edge-clear test for return-A topographic error in the prior-A arm.

The default command emits JSON on stdout. It never writes retained evidence.
Only the frozen canonical engine is imported; no other experiment module is
imported. Reduced configurations are explicitly labelled smoke experiments.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import inspect
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
EXPERIMENT_ID = "exp-20261009-95f07e14"
SCHEMA = "atmai.gng.return-edge-clear-topography/v1"
SEED_IDS = (0, 1, 2, 3, 4)
BOOTSTRAP_SEED = 202610099999
STREAM_IDS = {"initialization": 0, "warmup": 1, "intervention": 2, "return": 3, "heldout": 4}
ARMS = ("retained", "cleared")
A = (0.0, 0.0)
B = (2.5, 1.5)
SIGMA = 0.35
MAX_REPORT_BYTES = 5 * 1024 * 1024

if hashlib.sha256(ENGINE_PATH.read_bytes()).hexdigest() != ENGINE_SHA256:
    raise RuntimeError("canonical-gng-v1 source hash changed; this protocol requires its frozen engine")
_SPEC = importlib.util.spec_from_file_location("return_edge_clear_canonical_gng", ENGINE_PATH)
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
            "component_count": len(model.connected_components()),
            "isolated_node_count": len(model.isolated_nodes())}


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


class EdgeClearGNG(GrowingNeuralGas):
    """Canonical engine with exactly one check relaxed: isolated prototypes.

    The treatment empties the Hebbian edge set immediately before return-A
    learning, which by construction leaves every prototype without a neighbor.
    The canonical engine rejects that state inside ``step``. This subclass
    repeats every other canonical invariant verbatim and omits only the
    isolated-node clause, so no learning rule, parameter, insertion, or pruning
    decision changes.
    """

    def assert_invariants(self) -> None:
        if len(self._nodes) < 2:
            raise AssertionError("GNG must retain at least two nodes")
        if len(self._nodes) > self.parameters.max_nodes:
            raise AssertionError("node count exceeds max_nodes")
        for node_id, node in self._nodes.items():
            if node_id < 0 or len(node.vector) != self.dimension:
                raise AssertionError("invalid node identity or dimension")
            if (
                any(not math.isfinite(value) for value in node.vector)
                or not math.isfinite(node.error)
                or node.error < 0
            ):
                raise AssertionError("node state must be finite and non-negative")
        for edge, age in self._edge_ages.items():
            left, right = edge
            if left >= right or left not in self._nodes or right not in self._nodes:
                raise AssertionError("edges must be normalized and reference nodes")
            if not isinstance(age, int) or age < 0:
                raise AssertionError("edge ages must be non-negative integers")


def relax_isolated_node_check(model: GrowingNeuralGas) -> EdgeClearGNG:
    """Copy the full engine state into the single-override subclass."""

    clone = copy.deepcopy(model)
    clone.__class__ = EdgeClearGNG
    return clone


def overridden_methods() -> set[str]:
    """Names this experiment replaces on the frozen engine."""

    return {name for name, value in vars(EdgeClearGNG).items()
            if inspect.isfunction(value) and name in vars(GrowingNeuralGas)
            and value is not vars(GrowingNeuralGas)[name]}


def clear_edges(model: Any) -> dict[str, Any]:
    """Empty the Hebbian edge set, leaving every other piece of state alone."""

    before = full_state(model)
    model._edge_ages.clear()
    after = full_state(model)
    return {"edges_before": len(before["edges"]), "edges_after": len(after["edges"]),
            "nodes_identical_including_errors": before["nodes"] == after["nodes"],
            "parameters_identical": before["parameters"] == after["parameters"],
            "dimension_identical": before["dimension"] == after["dimension"],
            "samples_seen_identical": before["samples_seen"] == after["samples_seen"],
            "next_node_id_identical": before["next_node_id"] == after["next_node_id"],
            "isolated_nodes_after": len(model.isolated_nodes()),
            "node_count": len(model._nodes)}


def canonical_refusal(model: Any, signal: Sequence[float]) -> dict[str, Any]:
    """Ask the unchanged engine to take one step from a cleared copy of `model`."""

    probe = copy.deepcopy(model)
    probe.__class__ = GrowingNeuralGas
    if type(probe) is not GrowingNeuralGas:  # pragma: no cover - defensive
        raise AssertionError("the refusal probe must run the unchanged frozen engine")
    probe._edge_ages.clear()
    try:
        probe.step(signal)
    except (AssertionError, RuntimeError) as error:
        return {"engine_class": type(probe).__name__, "stepped": False,
                "cleared_isolated_nodes": len(probe.isolated_nodes()),
                "error_type": type(error).__name__, "message": str(error)}
    return {"engine_class": type(probe).__name__, "stepped": True,
            "cleared_isolated_nodes": len(probe.isolated_nodes()),
            "error_type": None, "message": None}


def measure_phase(model: Any, signals: Sequence[Sequence[float]], name: str) -> dict[str, Any]:
    """Score every sample before its update without window bookkeeping."""

    if not signals:
        raise ValueError("phase requires at least one sample")
    counts = [len(model._nodes)]
    total_qe = 0.0
    total_misses = 0
    churn = empty_churn()
    for signal in signals:
        qe, missing_edge = preupdate_errors(model, signal)
        total_qe += qe
        total_misses += missing_edge
        add_churn(churn, model.step(signal))
        counts.append(len(model._nodes))
    return {"name": name, "samples": len(signals), "mean_qe": total_qe / len(signals),
            "mean_te": total_misses / len(signals), "cumulative_qe": total_qe,
            "topographic_misses": total_misses, "capacity": capacity_summary(counts),
            "churn": churn, "final_edge_count": len(model._edge_ages),
            "final_isolated_node_count": len(model.isolated_nodes())}


def run_return_phase(model: Any, signals: Sequence[Sequence[float]], window_size: int,
                     name: str = "return") -> tuple[dict[str, Any], list[int], bool]:
    """Score the measured return phase in non-overlapping windows.

    A seed is retained rather than dropped: if the engine refuses a step, the
    completed windows, the failure, and the partial capacity trace are returned.
    """

    if not signals or len(signals) % window_size:
        raise ValueError("phase requires complete non-overlapping windows")
    windows: list[dict[str, Any]] = []
    counts = [len(model._nodes)]
    total_qe = 0.0
    total_misses = 0
    phase_churn = empty_churn()
    isolated_at_start = len(model.isolated_nodes())
    first_connected_sample = 0 if isolated_at_start == 0 else None
    failure: dict[str, Any] | None = None
    scored = 0
    for window_start in range(0, len(signals), window_size):
        window_qe: list[float] = []
        window_misses = 0
        window_churn = empty_churn()
        components_start = len(model.connected_components())
        for signal in signals[window_start:window_start + window_size]:
            qe, missing_edge = preupdate_errors(model, signal)
            try:
                result = model.step(signal)
            except (AssertionError, RuntimeError) as error:
                failure = {"error_type": type(error).__name__, "message": str(error),
                           "sample_index": window_start + len(window_qe),
                           "samples_scored": scored, "windows_completed": len(windows)}
                break
            window_qe.append(qe)
            window_misses += missing_edge
            scored += 1
            add_churn(window_churn, result)
            add_churn(phase_churn, result)
            counts.append(len(model._nodes))
            if first_connected_sample is None and not model.isolated_nodes():
                first_connected_sample = scored
        if failure is not None:
            break
        squared_loss = math.fsum(window_qe)
        total_qe += squared_loss
        total_misses += window_misses
        windows.append({"start_sample": window_start, "end_sample": window_start + window_size,
                        "mean_qe": squared_loss / window_size, "mean_te": window_misses / window_size,
                        "squared_loss": squared_loss, "topographic_misses": window_misses,
                        "cumulative_qe": total_qe,
                        "capacity": capacity_summary(counts[window_start:window_start + window_size + 1]),
                        "edge_count": len(model._edge_ages),
                        "isolated_nodes": len(model.isolated_nodes()),
                        "components_start": components_start, "components_end": len(model.connected_components()),
                        "churn": window_churn})
    phase = {"name": name, "samples": len(signals), "samples_scored": scored,
             "mean_qe": total_qe / scored if scored else None,
             "mean_te": total_misses / scored if scored else None,
             "cumulative_qe": total_qe, "topographic_misses": total_misses,
             "windows": windows, "churn": phase_churn,
             "isolated_nodes_at_start": isolated_at_start,
             "first_sample_without_isolated_nodes": first_connected_sample,
             "final_edge_count": len(model._edge_ages),
             "final_isolated_node_count": len(model.isolated_nodes()),
             "final_component_count": len(model.connected_components()),
             "failure": failure}
    return phase, counts, failure is None


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


def compare_traces(left: Sequence[int], right: Sequence[int]) -> dict[str, Any]:
    """Compare two capacity traces, keeping an unequal pair visible."""

    if len(left) != len(right) or len(left) < 2:
        return {"comparable": False, "exactly_matched": False,
                "reason": "the paired arms did not score the same number of samples",
                "retained_scored_samples": max(len(left) - 1, 0),
                "cleared_scored_samples": max(len(right) - 1, 0)}
    return {"comparable": True, **compare_capacities(left, right)}


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
    return {"n": n, "mean_return_te_difference": math.fsum(differences) / n,
            "ci95": [quantile(samples, 0.025), quantile(samples, 0.975)],
            "bootstrap_seed": seed, "bootstrap_resamples": resamples,
            "resampling_unit": "paired seed-level mean return topographic error difference",
            "quantile": "linear interpolation at p * (n - 1)",
            "interpretation": "descriptive percentile interval over this fixed five-seed synthetic panel"}


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
    for point in warmup_noise:
        warm_a.step(translate(point, A))
    warmup = state_summary(warm_a)
    warmup["reached_requested_capacity"] = warmup["node_count"] == config.max_nodes
    # Thresholds are frozen from the pre-change warm-A state, never from return.
    reference = evaluate_reference(warm_a, heldout)

    boundary = copy.deepcopy(warm_a)
    if full_state(boundary) != full_state(warm_a):
        raise AssertionError("cloning the warm-A state changed the full starting state")
    prior_a_intervention = measure_phase(boundary, [translate(point, B) for point in intervention_noise], "intervention")
    boundary_state = state_summary(boundary)

    return_signals = [translate(point, A) for point in return_noise]
    retained_model = copy.deepcopy(boundary)
    cleared_model = relax_isolated_node_check(boundary)
    for clone in (retained_model, cleared_model):
        if full_state(clone) != full_state(boundary):
            raise AssertionError("cloning the prior-A boundary state changed the full starting state")
    # Probed and compared before either arm takes a single return sample.
    refusal = canonical_refusal(boundary, return_signals[0])
    identical_before_treatment = full_state(cleared_model) == full_state(retained_model)
    clear_record = clear_edges(cleared_model)
    treated_state_differs = full_state(cleared_model) != full_state(boundary)
    retained_phase, retained_counts, retained_feasible = run_return_phase(
        retained_model, return_signals, config.window_size)
    cleared_phase, cleared_counts, cleared_feasible = run_return_phase(
        cleared_model, return_signals, config.window_size)

    capacity = compare_traces(retained_counts, cleared_counts)
    paired = retained_feasible and cleared_feasible
    te_difference = (cleared_phase["mean_te"] - retained_phase["mean_te"]) if paired else None
    qe_difference = (cleared_phase["mean_qe"] - retained_phase["mean_qe"]) if paired else None
    complete = (retained_phase["samples_scored"] == config.phase_steps
                and cleared_phase["samples_scored"] == config.phase_steps)
    for phase in (retained_phase, cleared_phase):
        phase["recovery"] = {"qe": recovery(phase["windows"], reference["qe_threshold"]),
                             "joint": recovery(phase["windows"], reference["qe_threshold"], reference["te_threshold"])}
    pairing = {"identical_state_before_treatment": identical_before_treatment,
               "nodes_and_errors_identical_after_treatment": clear_record["nodes_identical_including_errors"],
               "samples_seen_identical": clear_record["samples_seen_identical"],
               "next_node_id_identical": clear_record["next_node_id_identical"],
               "parameters_identical": clear_record["parameters_identical"],
               "edges_are_the_only_difference": treated_state_differs,
               "shared_return_signals_sha256": digest(return_signals),
               "both_arms_scored_every_return_sample": complete}
    return {"seed_id": seed_id, "stream_seeds": seeds,
            "stream_sha256": {"initialization_base_noise": digest(initialization),
                              "warmup_base_noise": digest(warmup_noise),
                              "intervention_base_noise": digest(intervention_noise),
                              "shared_return_signals": digest(return_signals), "heldout_A": digest(heldout)},
            "warmup": warmup, "prior_a_intervention": prior_a_intervention,
            "boundary_state": boundary_state, "reference": reference,
            "treatment": {"engine_class": type(cleared_model).__name__,
                          "overridden_engine_methods": sorted(overridden_methods()),
                          "canonical_refusal": refusal, "clear_record": clear_record},
            "arms": {
                "retained": {"engine_class": type(retained_model).__name__,
                             "boundary_state": boundary_state,
                             "measured_all_return_samples": retained_phase["samples_scored"] == config.phase_steps,
                             "feasible": retained_feasible, "phase": retained_phase},
                "cleared": {"engine_class": type(cleared_model).__name__,
                            "boundary_state": boundary_state,
                            "measured_all_return_samples": cleared_phase["samples_scored"] == config.phase_steps,
                            "feasible": cleared_feasible, "phase": cleared_phase},
            },
            "comparisons": {"return_te_difference_cleared_minus_retained": te_difference,
                            "return_qe_difference_cleared_minus_retained": qe_difference,
                            "te_difference_favours_clearing": None if te_difference is None else te_difference < 0,
                            "capacity": capacity,
                            "insertions_in_measured_phase": {"retained": retained_phase["churn"]["inserted_nodes"],
                                                              "cleared": cleared_phase["churn"]["inserted_nodes"]},
                            "node_removals_in_measured_phase": {"retained": retained_phase["churn"]["removed_nodes"],
                                                                 "cleared": cleared_phase["churn"]["removed_nodes"]}},
            "pairing": pairing,
            "capacity_matched": bool(capacity.get("exactly_matched")),
            "capacity_limits_isolated_interpretation": (not capacity.get("exactly_matched")
                                                          or not retained_feasible or not cleared_feasible
                                                          or not complete)}


def summarize(outcomes: Sequence[dict[str, Any]], config: Configuration) -> dict[str, Any]:
    differences = [outcome["comparisons"]["return_te_difference_cleared_minus_retained"] for outcome in outcomes
                   if outcome["comparisons"]["return_te_difference_cleared_minus_retained"] is not None]
    primary = paired_bootstrap(differences, config.bootstrap_resamples) if differences else {
        "n": 0, "mean_return_te_difference": None, "ci95": None,
        "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_resamples": config.bootstrap_resamples,
        "resampling_unit": "paired seed-level mean return topographic error difference",
        "quantile": "linear interpolation at p * (n - 1)",
        "interpretation": "no paired seed produced a comparable return measurement"}
    primary["seed_differences"] = [
        {"seed_id": outcome["seed_id"],
         "difference": outcome["comparisons"]["return_te_difference_cleared_minus_retained"]}
        for outcome in outcomes]
    primary["seeds_favouring_clearing"] = sum(1 for outcome in outcomes
                                              if outcome["comparisons"]["te_difference_favours_clearing"] is True)
    primary["seeds_favouring_retaining"] = sum(1 for outcome in outcomes
                                                if outcome["comparisons"]["te_difference_favours_clearing"] is False)
    primary["capacity_mismatch_seed_ids"] = [outcome["seed_id"] for outcome in outcomes if not outcome["capacity_matched"]]
    qe_differences = [outcome["comparisons"]["return_qe_difference_cleared_minus_retained"] for outcome in outcomes
                      if outcome["comparisons"]["return_qe_difference_cleared_minus_retained"] is not None]
    measured = {arm: [outcome["arms"][arm]["phase"]["mean_te"] for outcome in outcomes
                      if outcome["arms"][arm]["phase"]["mean_te"] is not None] for arm in ARMS}
    first_window = {arm: [outcome["arms"][arm]["phase"]["windows"][0]["mean_te"] for outcome in outcomes
                          if outcome["arms"][arm]["phase"]["windows"]] for arm in ARMS}
    return {"primary": primary,
            "mean_return_qe_difference": math.fsum(qe_differences) / len(qe_differences) if qe_differences else None,
            "mean_return_te": {arm: (math.fsum(values) / len(values)) if values else None
                               for arm, values in measured.items()},
            "mean_first_window_return_te": {arm: (math.fsum(values) / len(values)) if values else None
                                            for arm, values in first_window.items()},
            "feasibility": {
                "seed_count": len(outcomes),
                "canonical_refusal_seed_ids": [outcome["seed_id"] for outcome in outcomes
                                               if not outcome["treatment"]["canonical_refusal"]["stepped"]],
                "cleared_infeasible_seed_ids": [outcome["seed_id"] for outcome in outcomes if not outcome["arms"]["cleared"]["feasible"]],
                "isolated_nodes_after_clear": sorted({outcome["treatment"]["clear_record"]["isolated_nodes_after"]
                                                     for outcome in outcomes}),
                "cleared_node_removal_seed_ids": [outcome["seed_id"] for outcome in outcomes
                                                  if outcome["comparisons"]["node_removals_in_measured_phase"]["cleared"]],
                "cleared_insertion_seed_ids": [outcome["seed_id"] for outcome in outcomes
                                               if outcome["comparisons"]["insertions_in_measured_phase"]["cleared"]],
                "first_sample_without_isolated_nodes": [
                    {"seed_id": outcome["seed_id"],
                     "sample": outcome["arms"]["cleared"]["phase"]["first_sample_without_isolated_nodes"]}
                    for outcome in outcomes],
            },
            "recovery_counts": {arm: {metric: {"confirmed": sum(not outcome["arms"][arm]["phase"]["recovery"][metric]["censored"] for outcome in outcomes),
                                               "censored": sum(outcome["arms"][arm]["phase"]["recovery"][metric]["censored"] for outcome in outcomes)}
                                      for metric in ("qe", "joint")} for arm in ARMS},
            "claim_limits": ["Topographic error on synthetic geometry is measured; semantic identity, label handling, drift detection, and explicit memory are not evaluated.",
                             "Five paired seeds describe this fixed panel only; there is no aggregate pass/fail and no population claim.",
                             "The treatment is a complete Hebbian edge reset, not a selective B-region reset, so it also discards valid A-region adjacency.",
                             "Cleared edges leave prototypes isolated, which the unchanged engine rejects; the treatment arm therefore relaxes only the isolated-node assertion, and that deviation is recorded per seed.",
                             "Common node caps and matched traces are not evidence of matched resources; every capacity and removal count is retained.",
                             "A reduced topographic error does not establish concept identity or a usable memory mechanism."]}


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
                     "paired_design": "one warm-A model per seed is cloned twice at the end of the B intervention; only the Hebbian edge set differs at the return boundary",
                     "paired_invariance": "prototype positions, node errors, node count, next node id, sample count, and parameters are compared for exact equality; both arms consume the same return signals in the same order",
                     "treatment": "clear every edge immediately before return-A learning; nothing else is modified",
                     "engine_deviation": "EdgeClearGNG overrides assert_invariants only, omitting the isolated-node clause; the canonical engine refuses the cleared state, which is probed and recorded per seed",
                     "capacity_comparison": "preupdate node count for every scored sample plus every postupdate count; first_mismatch_step is one-based within the phase",
                     "thresholds": "independent warm-A heldout QE times 1.25 and min(1, warm-A heldout TE + 0.02), frozen before the return phase and shared by both arms",
                     "recovery": "two consecutive non-overlapping windows; onset is retrospective first-window start; confirmation is second-window end",
                     "failure_policy": "retain every seed; an arm the engine refuses to continue keeps its completed windows and its failure record",
                     "primary_estimand": "seed-mean return topographic error of the cleared arm minus the retained arm; negative favours clearing",
                     "predecessor_cross_check": "the retained arm reproduces the completed predecessor's prior-A arm for the same seed ids, data, and hyperparameters",
                     "fingerprint_normalization": "data and model-state fingerprints use canonical sorted-key JSON with floats rounded to 12 decimal places; source hashes remain byte-exact; within-run state checks use exact unrounded equality",
                     "rounding_decimal_places": 12},
        "provenance": {"engine_version": "canonical-gng-v1", "engine_path": ENGINE_PATH.relative_to(ROOT).as_posix(),
                       "engine_sha256": ENGINE_SHA256, "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       "predecessors": ["exp-20260907-8313df3e"],
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