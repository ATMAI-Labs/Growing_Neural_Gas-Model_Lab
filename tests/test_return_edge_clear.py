from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "labs" / "002-controlled-drift" / "experiments" / "exp-20261009-95f07e14-return-edge-clear-topography"
RUNNER_PATH = EXPERIMENT / "run.py"
PREDECESSOR_RESULT = (ROOT / "labs" / "002-controlled-drift" / "experiments"
                      / "exp-20260907-8313df3e-capacity-controlled-recurrence"
                      / "results" / "capacity-controlled-recurrence.json")
SPEC = importlib.util.spec_from_file_location("return_edge_clear_runner", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


def smoke_config(**overrides: object):
    values = {"seed_ids": (0, 1), "warmup_steps": 600, "phase_steps": 64,
              "window_size": 16, "evaluation_points": 64, "max_nodes": 6,
              "bootstrap_resamples": 100}
    values.update(overrides)
    return RUNNER.Configuration(**values)


def trained_model(seed: int = 7, steps: int = 600, max_nodes: int = 6):
    model = RUNNER.GrowingNeuralGas([(0.0, 0.0), (2.0, 0.0)], RUNNER.GNGParameters(max_nodes=max_nodes))
    for point in RUNNER.gaussian_noise(seed, steps):
        model.step(point)
    return model


class EdgeClearTreatmentTests(unittest.TestCase):
    def test_scores_both_metrics_before_update(self) -> None:
        model = RUNNER.GrowingNeuralGas([(0.0, 0.0), (2.0, 0.0)], RUNNER.GNGParameters(max_nodes=2))

        phase, counts, feasible = RUNNER.run_return_phase(model, [(1.0, 0.0)], 1)

        # Before learning: nearest squared distance is 1 and no edge connects the pair.
        self.assertTrue(feasible)
        self.assertEqual(phase["mean_qe"], 1.0)
        self.assertEqual(phase["mean_te"], 1.0)
        self.assertLess(model.mean_squared_quantization_error([(1.0, 0.0)]), 1.0)
        self.assertEqual(model.topographic_error([(1.0, 0.0)]), 0.0)
        self.assertEqual(counts, [2, 2])
        self.assertIsNone(phase["failure"])
        self.assertEqual(phase["windows"][0]["mean_te"], 1.0)

    def test_clearing_edges_changes_only_the_edge_set(self) -> None:
        model = trained_model()
        edges_before = len(model._edge_ages)
        self.assertGreater(edges_before, 0)

        record = RUNNER.clear_edges(model)

        self.assertEqual(record["edges_before"], edges_before)
        self.assertEqual(record["edges_after"], 0)
        self.assertEqual(model._edge_ages, {})
        self.assertEqual(record["isolated_nodes_after"], record["node_count"])
        for field in ("nodes_identical_including_errors", "parameters_identical", "dimension_identical",
                      "samples_seen_identical", "next_node_id_identical"):
            self.assertTrue(record[field], field)
        self.assertEqual(model.isolated_nodes(), tuple(sorted(model._nodes)))

    def test_relaxation_overrides_only_the_isolated_node_assertion(self) -> None:
        self.assertEqual(RUNNER.overridden_methods(), {"assert_invariants"})

        relaxed = RUNNER.relax_isolated_node_check(trained_model())
        self.assertIsInstance(relaxed, RUNNER.EdgeClearGNG)
        self.assertEqual(RUNNER.full_state(relaxed), RUNNER.full_state(trained_model()))

        RUNNER.clear_edges(relaxed)
        relaxed.assert_invariants()  # the only clause the treatment drops
        for node_id in sorted(relaxed._nodes)[:-1]:
            del relaxed._nodes[node_id]
        with self.assertRaisesRegex(AssertionError, "at least two nodes"):
            relaxed.assert_invariants()
        relaxed._nodes = {0: RUNNER.ENGINE.Node([0.0, 0.0]), 1: RUNNER.ENGINE.Node([1.0, 0.0])}
        relaxed._edge_ages = {}
        for index in range(1, 7):
            relaxed._nodes[index] = RUNNER.ENGINE.Node([0.0, 0.0])
        relaxed._next_node_id = 6
        with self.assertRaisesRegex(AssertionError, "node count exceeds max_nodes"):
            relaxed.assert_invariants()
        relaxed._nodes = {0: RUNNER.ENGINE.Node([0.0, 0.0]), 1: RUNNER.ENGINE.Node([1.0, 0.0])}
        relaxed._edge_ages = {(0, 1): -1}
        with self.assertRaisesRegex(AssertionError, "edge ages must be non-negative"):
            relaxed.assert_invariants()

    def test_canonical_engine_refuses_the_cleared_state_without_mutating_it(self) -> None:
        model = trained_model()

        refusal = RUNNER.canonical_refusal(model, (0.5, 0.5))

        self.assertEqual(refusal["engine_class"], "GrowingNeuralGas")
        self.assertFalse(refusal["stepped"])
        self.assertEqual(refusal["error_type"], "AssertionError")
        self.assertIn("isolated nodes", refusal["message"])
        self.assertGreater(refusal["cleared_isolated_nodes"], 0)
        self.assertTrue(model._edge_ages)  # the refusal probe works on a copy

        # The probe reports the unchanged engine even when handed a relaxed arm.
        relaxed = RUNNER.relax_isolated_node_check(model)
        self.assertFalse(RUNNER.canonical_refusal(relaxed, (0.5, 0.5))["stepped"])
        self.assertEqual(RUNNER.full_state(relaxed), RUNNER.full_state(model))

    def test_a_forced_insertion_after_clearing_is_refused_and_retained(self) -> None:
        # Fewer nodes than the cap, so insertion is due during the measured phase.
        outcome = RUNNER.run_seed((0, smoke_config(seed_ids=(0,), warmup_steps=120, max_nodes=100,
                                                  evaluation_points=16, bootstrap_resamples=10)))

        cleared = outcome["arms"]["cleared"]
        self.assertFalse(cleared["feasible"])
        self.assertEqual(cleared["phase"]["failure"]["error_type"], "RuntimeError")
        self.assertEqual(outcome["arms"]["retained"]["feasible"], True)
        self.assertLess(cleared["phase"]["samples_scored"], smoke_config().phase_steps)
        self.assertEqual(outcome["comparisons"]["return_te_difference_cleared_minus_retained"], None)
        self.assertFalse(outcome["comparisons"]["capacity"]["comparable"])
        self.assertTrue(outcome["capacity_limits_isolated_interpretation"])

    def test_paired_arms_differ_only_in_the_edge_set(self) -> None:
        outcome = RUNNER.run_seed((0, smoke_config(seed_ids=(0,))))

        pairing = outcome["pairing"]
        self.assertTrue(pairing["identical_state_before_treatment"])
        self.assertTrue(pairing["edges_are_the_only_difference"])
        for field in ("nodes_and_errors_identical_after_treatment", "samples_seen_identical",
                      "next_node_id_identical", "parameters_identical", "both_arms_scored_every_return_sample"):
            self.assertTrue(pairing[field], field)
        self.assertEqual(pairing["shared_return_signals_sha256"], outcome["stream_sha256"]["shared_return_signals"])
        self.assertEqual(outcome["arms"]["retained"]["boundary_state"], outcome["arms"]["cleared"]["boundary_state"])
        self.assertEqual(outcome["arms"]["retained"]["engine_class"], "GrowingNeuralGas")
        self.assertEqual(outcome["arms"]["cleared"]["engine_class"], "EdgeClearGNG")
        self.assertEqual(outcome["treatment"]["overridden_engine_methods"], ["assert_invariants"])

    def test_capacity_match_and_isolated_node_accounting(self) -> None:
        outcome = RUNNER.run_seed((1, smoke_config(seed_ids=(1,))))

        self.assertEqual(outcome["boundary_state"]["isolated_node_count"], 0)
        self.assertEqual(outcome["treatment"]["clear_record"]["isolated_nodes_after"],
                         outcome["boundary_state"]["node_count"])
        capacity = outcome["comparisons"]["capacity"]
        self.assertTrue(capacity["comparable"])
        self.assertTrue(capacity["exactly_matched"])
        self.assertEqual(capacity["mismatched_steps"], 0)
        self.assertEqual(capacity["postupdate_mismatched_steps"], 0)
        self.assertIsNone(capacity["first_mismatch_step"])
        self.assertEqual(outcome["comparisons"]["node_removals_in_measured_phase"], {"retained": 0, "cleared": 0})
        self.assertEqual(outcome["comparisons"]["insertions_in_measured_phase"], {"retained": 0, "cleared": 0})
        self.assertTrue(outcome["capacity_matched"])
        self.assertFalse(outcome["capacity_limits_isolated_interpretation"])
        self.assertEqual(outcome["arms"]["retained"]["phase"]["first_sample_without_isolated_nodes"], 0)

    def test_window_metrics_agree_with_the_phase_totals(self) -> None:
        outcome = RUNNER.run_seed((0, smoke_config(seed_ids=(0,), warmup_steps=600, phase_steps=64)))

        for arm in RUNNER.ARMS:
            phase = outcome["arms"][arm]["phase"]
            self.assertEqual(len(phase["windows"]), 4)
            self.assertAlmostEqual(phase["mean_qe"] * phase["samples"], phase["cumulative_qe"])
            self.assertAlmostEqual(sum(window["squared_loss"] for window in phase["windows"]),
                                   phase["cumulative_qe"])
            for index, window in enumerate(phase["windows"]):
                self.assertEqual(window["start_sample"], index * 16)
                self.assertEqual(window["end_sample"], (index + 1) * 16)
                self.assertEqual(window["topographic_misses"] / 16, window["mean_te"])
                self.assertLessEqual(window["capacity"]["max"], 6)
            self.assertEqual(phase["churn"]["inserted_nodes"], 0)
            self.assertEqual(phase["churn"]["removed_nodes"], 0)

    def test_measurement_never_mutates_the_model_it_scores(self) -> None:
        model = trained_model()
        starting = RUNNER.full_state(model)

        reference = RUNNER.evaluate_reference(model, RUNNER.gaussian_noise(11, 20))

        self.assertEqual(RUNNER.full_state(model), starting)
        self.assertEqual(reference["qe_threshold"], 1.25 * reference["heldout_mean_qe"])
        self.assertEqual(reference["te_threshold"], min(1.0, reference["heldout_te"] + 0.02))
        clone = copy.deepcopy(model)
        clone.step((4.0, 3.0))
        self.assertEqual(RUNNER.full_state(model), starting)
        self.assertNotEqual(RUNNER.digest(RUNNER.full_state(clone)), RUNNER.digest(starting))

    def test_summary_counts_every_seed_and_declares_no_verdict(self) -> None:
        report = RUNNER.build_report(smoke_config())
        summary = report["summary"]

        self.assertEqual(report["configuration_kind"], "smoke")
        self.assertEqual([outcome["seed_id"] for outcome in report["seed_outcomes"]], [0, 1])
        self.assertEqual(summary["primary"]["n"], 2)
        self.assertEqual(len(summary["primary"]["seed_differences"]), 2)
        self.assertEqual(summary["primary"]["seeds_favouring_clearing"]
                         + summary["primary"]["seeds_favouring_retaining"]
                         + len(summary["primary"]["capacity_mismatch_seed_ids"]), 2)
        self.assertEqual(summary["feasibility"]["seed_count"], 2)
        self.assertEqual(summary["feasibility"]["canonical_refusal_seed_ids"], [0, 1])
        self.assertTrue(any("no aggregate pass/fail" in limit for limit in summary["claim_limits"]))
        self.assertTrue(any("isolated-node assertion" in limit for limit in summary["claim_limits"]))
        self.assertLess(len(RUNNER.encode_report(report).encode()), 5 * 1024 * 1024)

    def test_bootstrap_and_recovery_use_the_declared_rules(self) -> None:
        self.assertEqual(RUNNER.quantile([0.0, 10.0], 0.025), 0.25)
        self.assertEqual(RUNNER.quantile([0.0, 10.0], 0.975), 9.75)
        constant = RUNNER.paired_bootstrap([0.04] * 5, 100)
        self.assertEqual(constant["n"], 5)
        self.assertEqual(constant["mean_return_te_difference"], 0.04)
        self.assertEqual(constant["ci95"], [0.04, 0.04])
        self.assertEqual(constant["bootstrap_seed"], RUNNER.BOOTSTRAP_SEED)
        self.assertNotIn(RUNNER.BOOTSTRAP_SEED,
                         [RUNNER.stream_seed(seed, stream) for seed in RUNNER.SEED_IDS for stream in RUNNER.STREAM_IDS])
        windows = [{"start_sample": index * 256, "end_sample": (index + 1) * 256,
                    "mean_qe": qe, "mean_te": te}
                   for index, (qe, te) in enumerate(((0.2, 0.40), (0.10, 0.01), (0.10, 0.01)))]
        joint = RUNNER.recovery(windows, 0.15, 0.03)
        self.assertEqual(joint["onset_samples"], 256)
        self.assertEqual(joint["confirmation_samples"], 768)
        self.assertFalse(joint["censored"])
        self.assertTrue(RUNNER.recovery(windows, 0.15, 0.0)["censored"])

    def test_unequal_capacity_traces_stay_visible(self) -> None:
        compared = RUNNER.compare_traces([3, 3, 3], [3, 3, 3])
        self.assertTrue(compared["comparable"])
        self.assertTrue(compared["exactly_matched"])
        unequal = RUNNER.compare_traces([3, 3, 3], [3, 2])
        self.assertFalse(unequal["comparable"])
        self.assertFalse(unequal["exactly_matched"])
        self.assertEqual(unequal["retained_scored_samples"], 2)
        self.assertEqual(unequal["cleared_scored_samples"], 1)

    def test_rejects_invalid_sizes_and_duplicate_seed_weighting(self) -> None:
        for overrides in ({"phase_steps": 63}, {"phase_steps": 16}, {"window_size": 0},
                          {"warmup_steps": -1}, {"evaluation_points": 0}, {"max_nodes": 1},
                          {"max_nodes": True}, {"seed_ids": (0, 0)}, {"seed_ids": ()},
                          {"seed_ids": (-1,)}, {"bootstrap_resamples": 0}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                smoke_config(**overrides)

    def test_preregistered_smoke_fixture_matches_except_environment(self) -> None:
        fixture = json.loads((EXPERIMENT / "fixtures" / "smoke.json").read_text())
        actual = RUNNER.build_report(smoke_config())
        del fixture["environment"]
        del actual["environment"]

        self.assertEqual(actual, fixture)
        self.assertEqual(actual["configuration"]["seed_ids"], [0, 1])

    def test_retained_arm_reproduces_the_frozen_predecessor(self) -> None:
        current = json.loads((EXPERIMENT / "results" / "edge-clear-return-topography.json").read_text())
        previous = json.loads(PREDECESSOR_RESULT.read_text())

        self.assertEqual([outcome["seed_id"] for outcome in current["seed_outcomes"]],
                         [outcome["seed_id"] for outcome in previous["seed_outcomes"]][:5])
        for outcome, prior in zip(current["seed_outcomes"], previous["seed_outcomes"]):
            abrupt = prior["arms"]["abrupt"]
            self.assertEqual(outcome["prior_a_intervention"]["mean_qe"], abrupt["phases"][0]["mean_qe"])
            self.assertEqual(outcome["arms"]["retained"]["phase"]["mean_qe"], abrupt["phases"][1]["mean_qe"])
            self.assertEqual(outcome["arms"]["retained"]["phase"]["mean_te"], abrupt["phases"][1]["mean_te"])
            self.assertEqual([window["mean_qe"] for window in outcome["arms"]["retained"]["phase"]["windows"]],
                             [window["mean_qe"] for window in abrupt["phases"][1]["windows"]])
            self.assertEqual(outcome["reference"]["qe_threshold"], prior["reference"]["qe_threshold"])
            self.assertEqual(outcome["reference"]["te_threshold"], prior["reference"]["te_threshold"])
            self.assertEqual(outcome["arms"]["retained"]["phase"]["recovery"]["qe"],
                             abrupt["phases"][1]["recovery"]["qe"])

    def test_parallel_cli_preserves_seed_order_and_deterministic_measurements(self) -> None:
        command = [sys.executable, str(RUNNER_PATH), "--seeds", "1,0", "--warmup-steps", "600",
                   "--phase-steps", "64", "--window-size", "16", "--evaluation-points", "64",
                   "--max-nodes", "6", "--bootstrap-resamples", "100", "--workers", "2", "--stdout"]

        result = subprocess.run(command, check=True, text=True, capture_output=True)
        parallel = json.loads(result.stdout)
        sequential = RUNNER.build_report(smoke_config(seed_ids=(1, 0)))

        self.assertEqual([outcome["seed_id"] for outcome in parallel["seed_outcomes"]], [1, 0])
        del parallel["environment"]
        del sequential["environment"]
        self.assertEqual(parallel, sequential)

    def test_optional_output_refuses_overwrites_and_experiment_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new.json"
            RUNNER.write_new_output(path, "first\n")
            with self.assertRaises(FileExistsError):
                RUNNER.write_new_output(path, "replacement\n")
            self.assertEqual(path.read_text(), "first\n")
        with self.assertRaises(ValueError):
            RUNNER.write_new_output(EXPERIMENT / "results" / "unsafe.json", "{}")


if __name__ == "__main__":
    unittest.main()