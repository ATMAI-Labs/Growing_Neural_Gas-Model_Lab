from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "labs" / "002-controlled-drift" / "experiments" / "exp-20260907-8313df3e-capacity-controlled-recurrence" / "run.py"
SPEC = importlib.util.spec_from_file_location("capacity_controlled_recurrence_runner", RUNNER_PATH)
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


class CapacityControlledRecurrenceTests(unittest.TestCase):
    def test_scores_both_metrics_before_update(self) -> None:
        model = RUNNER.GrowingNeuralGas([(0.0, 0.0), (2.0, 0.0)], RUNNER.GNGParameters(max_nodes=2))

        phase, counts = RUNNER.run_phase(model, [(1.0, 0.0)], 1, "intervention")

        # Before learning: nearest squared distance is 1 and there is no edge.
        # The update moves a node toward the sample and creates that edge.
        self.assertEqual(phase["mean_qe"], 1.0)
        self.assertEqual(phase["mean_te"], 1.0)
        self.assertLess(model.mean_squared_quantization_error([(1.0, 0.0)]), 1.0)
        self.assertEqual(model.topographic_error([(1.0, 0.0)]), 0.0)
        self.assertEqual(counts, [2, 2])

    def test_full_state_clone_and_heldout_evaluation_preserve_history(self) -> None:
        model = RUNNER.GrowingNeuralGas([(0.0, 0.0), (1.0, 0.0)])
        for signal in RUNNER.gaussian_noise(11, 250):
            model.step(signal)
        starting = RUNNER.full_state(model)
        clone = copy.deepcopy(model)
        self.assertEqual(RUNNER.full_state(clone), starting)
        self.assertEqual(set(starting), {"parameters", "dimension", "samples_seen", "next_node_id", "nodes", "edges"})
        self.assertTrue(any(node["error"] > 0 for node in starting["nodes"]))
        self.assertTrue(starting["edges"])

        reference = RUNNER.evaluate_reference(model, RUNNER.gaussian_noise(12, 20))

        self.assertEqual(RUNNER.full_state(model), starting)
        self.assertEqual(reference["qe_threshold"], 1.25 * reference["heldout_mean_qe"])
        self.assertEqual(reference["te_threshold"], min(1, reference["heldout_te"] + 0.02))
        clone.step((4.0, 3.0))
        self.assertEqual(RUNNER.full_state(model), starting)
        self.assertNotEqual(RUNNER.digest(RUNNER.full_state(clone)), RUNNER.digest(starting))

    def test_random_streams_and_return_signals_are_paired(self) -> None:
        seeds = [RUNNER.stream_seed(seed_id, stream) for seed_id in range(20) for stream in RUNNER.STREAM_IDS]
        self.assertEqual(len(set(seeds)), 100)
        self.assertEqual(RUNNER.stream_seed(3, "return"), 202609070303)
        self.assertNotIn(RUNNER.BOOTSTRAP_SEED, seeds)
        noise = RUNNER.gaussian_noise(RUNNER.stream_seed(0, "return"), 5)
        returns = [RUNNER.phase_signals(arm, "return", noise) for arm in RUNNER.ARMS]
        self.assertTrue(all(signals == returns[0] for signals in returns))
        self.assertEqual(RUNNER.phase_signals("abrupt", "intervention", noise), RUNNER.phase_signals("b_only", "intervention", noise))
        gradual = RUNNER.phase_signals("gradual", "intervention", noise)
        self.assertEqual(gradual[0], noise[0])
        self.assertEqual(gradual[-1], RUNNER.translate(noise[-1], RUNNER.B))
        self.assertEqual(gradual[2], RUNNER.translate(noise[2], (1.25, 0.75)))

    def test_fingerprint_normalization_does_not_weaken_exact_state_checks(self) -> None:
        self.assertEqual(RUNNER.digest([-0.0, -1e-14]), RUNNER.digest([0.0, 0.0]))
        model = RUNNER.GrowingNeuralGas([(0.1, 0.0), (1.0, 0.0)])
        original = RUNNER.full_state(model)
        perturbed = copy.deepcopy(original)
        perturbed["nodes"][0]["vector"][0] += 1e-14
        self.assertNotEqual(original, perturbed)
        self.assertEqual(RUNNER.digest(original), RUNNER.digest(perturbed))
        measure = RUNNER.preupdate_errors

        def mutating_measurement(current_model, signal):
            result = measure(current_model, signal)
            current_model._nodes[0].vector[0] += 1e-14
            return result

        with patch.object(RUNNER, "preupdate_errors", side_effect=mutating_measurement):
            with self.assertRaisesRegex(AssertionError, "evaluation changed"):
                RUNNER.evaluate_reference(model, [(0.2, 0.0)])

    def test_preregistered_smoke_fixture_matches_except_environment(self) -> None:
        fixture = json.loads((RUNNER_PATH.parent / "fixtures" / "smoke.json").read_text())
        actual = RUNNER.build_report(smoke_config())
        del fixture["environment"]
        del actual["environment"]

        self.assertEqual(actual, fixture)

    def test_capacity_comparison_detects_each_scored_and_postupdate_mismatch(self) -> None:
        comparison = RUNNER.compare_capacities([5, 5, 4, 5], [5, 4, 4, 4])

        self.assertEqual(comparison["compared_steps"], 3)
        self.assertEqual(comparison["mismatched_steps"], 1)
        self.assertEqual(comparison["first_mismatch_step"], 2)
        self.assertEqual(comparison["postupdate_mismatched_steps"], 2)
        self.assertEqual(comparison["first_postupdate_mismatch_step"], 1)
        self.assertFalse(comparison["exactly_matched"])
        self.assertTrue(RUNNER.compare_capacities([3, 2, 3], [3, 2, 3])["exactly_matched"])

    def test_recovery_distinguishes_retrospective_onset_confirmation_and_censoring(self) -> None:
        windows = [{"start_sample": index * 256, "end_sample": (index + 1) * 256,
                    "mean_qe": qe, "mean_te": te}
                   for index, (qe, te) in enumerate(((1.0, 0.0), (0.8, 0.0), (0.7, 0.5)))]

        qe = RUNNER.recovery(windows, 0.9)
        joint = RUNNER.recovery(windows, 0.9, 0.02)

        self.assertEqual(qe["onset_samples"], 256)
        self.assertEqual(qe["confirmation_samples"], 768)
        self.assertFalse(qe["censored"])
        self.assertTrue(joint["censored"])
        self.assertIsNone(joint["onset_samples"])
        self.assertIsNone(joint["confirmation_samples"])
        self.assertEqual(joint["horizon_samples"], 768)
        immediate = RUNNER.recovery(windows, 1.0)
        self.assertEqual(immediate["onset_samples"], 0)
        self.assertEqual(immediate["confirmation_samples"], 512)

    def test_bootstrap_resamples_seed_differences_and_uses_declared_quantiles(self) -> None:
        self.assertEqual(RUNNER.quantile([0.0, 10.0], 0.025), 0.25)
        self.assertEqual(RUNNER.quantile([0.0, 10.0], 0.975), 9.75)
        constant = RUNNER.paired_bootstrap([-0.5] * 20, 100)
        self.assertEqual(constant["n"], 20)
        self.assertEqual(constant["mean_return_qe_difference"], -0.5)
        self.assertEqual(constant["ci95"], [-0.5, -0.5])
        first = RUNNER.paired_bootstrap([-1.0, 0.0, 2.0], 100)
        second = RUNNER.paired_bootstrap([-1.0, 0.0, 2.0], 100)
        self.assertEqual(first, second)
        self.assertAlmostEqual(first["mean_return_qe_difference"], 1 / 3)
        self.assertEqual(first["bootstrap_seed"], 202609079999)

    def test_seed_outcome_keeps_full_state_pairing_exposures_and_capacity_accounting(self) -> None:
        config = smoke_config(seed_ids=(0,))
        outcome = RUNNER.run_seed((0, config))
        arms = outcome["arms"]
        self.assertEqual(arms["stationary"]["starting_state"], arms["abrupt"]["starting_state"])
        self.assertEqual(arms["stationary"]["starting_state"], arms["gradual"]["starting_state"])
        self.assertEqual(outcome["reference"]["state_sha256_before_and_after"], outcome["warmup"]["a"]["sha256"])
        self.assertEqual(arms["abrupt"]["exposure"]["intervention"]["exact_B"], arms["b_only"]["exposure"]["intervention"]["exact_B"])
        self.assertEqual(arms["abrupt"]["exposure"]["total_exact_B_samples"], config.phase_steps)
        self.assertEqual(arms["b_only"]["exposure"]["total_exact_B_samples"], config.warmup_steps + config.phase_steps)
        self.assertEqual(arms["gradual"]["exposure"]["intervention"]["exact_B"], 1)
        for arm in arms.values():
            self.assertEqual(arm["final_state"]["samples_seen"], config.warmup_steps + 2 * config.phase_steps)
            for phase in arm["phases"]:
                self.assertEqual(len(phase["windows"]), 4)
                self.assertAlmostEqual(phase["mean_qe"] * config.phase_steps, phase["cumulative_qe"])
                for record in [phase] + phase["windows"]:
                    cap, churn = record["capacity"], record["churn"]
                    self.assertEqual(cap["start"] + churn["inserted_nodes"] - churn["removed_nodes"], cap["end"])
                    self.assertLessEqual(cap["max"], config.max_nodes)
                    self.assertLessEqual(cap["min"], cap["end"])
        for pair in outcome["comparisons"]["primary_capacity_by_phase"].values():
            self.assertEqual(pair["compared_steps"], config.phase_steps)

    def test_short_warmup_capacity_failures_are_retained(self) -> None:
        report = RUNNER.build_report(smoke_config(seed_ids=(0,), warmup_steps=1))

        self.assertEqual([outcome["seed_id"] for outcome in report["seed_outcomes"]], [0])
        self.assertTrue(report["seed_outcomes"][0]["warmup"]["starting_capacity_failure"])
        self.assertEqual(report["summary"]["primary"]["warmup_capacity_failure_seed_ids"], [0])
        self.assertTrue(report["seed_outcomes"][0]["capacity_limits_capacity_isolated_interpretation"])

    def test_smoke_report_is_deterministic_and_all_seeds_are_retained(self) -> None:
        config = smoke_config()
        first = RUNNER.build_report(config)
        second = RUNNER.build_report(config)

        self.assertEqual(first, second)
        self.assertEqual(first["configuration_kind"], "smoke")
        self.assertEqual(first["schema"], RUNNER.SCHEMA)
        self.assertEqual([outcome["seed_id"] for outcome in first["seed_outcomes"]], [0, 1])
        self.assertEqual(first["summary"]["primary"]["n"], 2)
        self.assertEqual(len(first["summary"]["primary"]["seed_differences"]), 2)
        self.assertLess(len(RUNNER.encode_report(first).encode()), 5 * 1024 * 1024)

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

    def test_rejects_invalid_sizes_and_duplicate_seed_weighting(self) -> None:
        for overrides in ({"phase_steps": 63}, {"phase_steps": 16}, {"window_size": 0},
                          {"warmup_steps": -1}, {"evaluation_points": 0}, {"max_nodes": 1},
                          {"max_nodes": True}, {"seed_ids": (0, 0)}, {"seed_ids": ()},
                          {"seed_ids": (-1,)}, {"bootstrap_resamples": 0}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                smoke_config(**overrides)

    def test_optional_output_refuses_overwrites_and_experiment_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new.json"
            RUNNER.write_new_output(path, "first\n")
            with self.assertRaises(FileExistsError):
                RUNNER.write_new_output(path, "replacement\n")
            self.assertEqual(path.read_text(), "first\n")
        with self.assertRaises(ValueError):
            RUNNER.write_new_output(RUNNER_PATH.parent / "results" / "unsafe.json", "{}")


if __name__ == "__main__":
    unittest.main()
