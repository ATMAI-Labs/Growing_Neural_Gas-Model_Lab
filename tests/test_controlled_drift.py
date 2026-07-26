from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = (
    REPOSITORY_ROOT
    / "labs"
    / "002-controlled-drift"
    / "experiments"
    / "exp-20260727-eee720cf-frozen-baseline-drift"
    / "run.py"
)
RESULT_PATH = RUNNER_PATH.parent / "results" / "controlled-drift.json"
MANIFEST_PATH = RUNNER_PATH.parent / "experiment.json"
MODULE_NAME = "controlled_drift_runner"
MODULE_SPEC = importlib.util.spec_from_file_location(MODULE_NAME, RUNNER_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise ImportError(f"could not load controlled-drift runner from {RUNNER_PATH}")
RUNNER = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_NAME] = RUNNER
MODULE_SPEC.loader.exec_module(RUNNER)


class ControlledDriftTests(unittest.TestCase):
    def test_prequential_observation_reads_state_without_updating_it(self) -> None:
        model = RUNNER.GrowingNeuralGas(
            [[0.0], [10.0]],
            RUNNER.GNGParameters(
                insertion_interval=100,
                winner_learning_rate=0.5,
                neighbor_learning_rate=0.25,
                error_decay=1.0,
            ),
        )

        observation = RUNNER.prequential_observation(model, [4.0])

        self.assertEqual(observation[RUNNER.QE_KEY], 16.0)
        self.assertEqual(observation[RUNNER.TE_KEY], 1.0)
        self.assertEqual(model.samples_seen, 0)
        self.assertEqual(model.node_vectors, {0: (0.0,), 1: (10.0,)})
        self.assertEqual(model.edge_ages, {})

        model.step([4.0])
        post_update = RUNNER.prequential_observation(model, [4.0])
        self.assertEqual(post_update[RUNNER.QE_KEY], 4.0)
        self.assertEqual(post_update[RUNNER.TE_KEY], 0.0)

    def test_recovery_delay_requires_consecutive_qualifying_windows(self) -> None:
        windows = [
            {"start_step": 100, RUNNER.QE_KEY: 2.0},
            {"start_step": 200, RUNNER.QE_KEY: 0.9},
            {"start_step": 300, RUNNER.QE_KEY: 1.1},
            {"start_step": 400, RUNNER.QE_KEY: 0.8},
            {"start_step": 500, RUNNER.QE_KEY: 0.7},
        ]

        self.assertEqual(RUNNER.recovery_delay(windows, 1.0), 300)
        self.assertIsNone(RUNNER.recovery_delay(windows[:4], 1.0))
        with self.assertRaises(ValueError):
            RUNNER.recovery_delay(windows, 1.0, consecutive=0)

    def test_report_is_bounded_deterministic_and_scores_every_clause(self) -> None:
        report = RUNNER.build_report(steps_per_phase=256, window_size=128)
        repeated = RUNNER.build_report(steps_per_phase=256, window_size=128)

        self.assertEqual(report, repeated)
        self.assertEqual(report["schema"], "atmai.gng.controlled-drift/v1")
        self.assertEqual(report["protocol"]["steps_per_phase"], 256)
        self.assertEqual(report["protocol"]["window_size"], 128)
        self.assertEqual(
            report["source_sha256"]["atmai_gng/gng.py"],
            RUNNER.EXPECTED_GNG_SHA256,
        )
        self.assertEqual(
            [scenario["scenario_id"] for scenario in report["scenarios"]],
            [
                "abrupt_translation",
                "gradual_translation",
                "abrupt_rotation_90",
                "abrupt_mixture_reweighting",
                "recurring_translation_aba",
            ],
        )
        self.assertEqual(
            len(report["hypothesis_evaluation"]["clauses"]),
            5,
        )
        self.assertIsNone(report["hypothesis_evaluation"]["aggregate_pass"])

        for scenario in report["scenarios"]:
            expected_windows = (
                len(scenario["schedule"]["phases"])
                * report["protocol"]["steps_per_phase"]
                // report["protocol"]["window_size"]
            )
            self.assertEqual(len(scenario["windows"]), expected_windows)
            self.assertEqual(
                scenario["schedule"]["total_steps"],
                sum(window["sample_count"] for window in scenario["windows"]),
            )
            self.assertEqual(scenario["final_graph"]["isolates"], 0)
            for window in scenario["windows"]:
                quantization_error = window[RUNNER.QE_KEY]
                topographic_error = window[RUNNER.TE_KEY]
                self.assertTrue(math.isfinite(quantization_error))
                self.assertGreaterEqual(quantization_error, 0.0)
                self.assertGreaterEqual(topographic_error, 0.0)
                self.assertLessEqual(topographic_error, 1.0)

    def test_size_validation_rejects_partial_windows(self) -> None:
        with self.assertRaises(ValueError):
            RUNNER.build_report(steps_per_phase=0, window_size=128)
        with self.assertRaises(ValueError):
            RUNNER.build_report(steps_per_phase=256, window_size=0)
        with self.assertRaises(ValueError):
            RUNNER.build_report(steps_per_phase=257, window_size=128)

    def test_retained_result_is_bound_to_the_default_runner(self) -> None:
        report = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        runner_digest = hashlib.sha256(RUNNER_PATH.read_bytes()).hexdigest()

        self.assertEqual(report["schema"], RUNNER.SCHEMA)
        self.assertEqual(report["experiment_id"], RUNNER.EXPERIMENT_ID)
        self.assertEqual(report["experiment_id"], manifest["id"])
        self.assertEqual(
            report["protocol"]["steps_per_phase"],
            RUNNER.DEFAULT_STEPS_PER_PHASE,
        )
        self.assertEqual(
            report["protocol"]["window_size"],
            RUNNER.DEFAULT_WINDOW_SIZE,
        )
        self.assertEqual(report["source_sha256"]["run.py"], runner_digest)
        self.assertEqual(
            report["source_sha256"]["atmai_gng/gng.py"],
            RUNNER.EXPECTED_GNG_SHA256,
        )
        self.assertEqual(
            [clause["passed"] for clause in report["hypothesis_evaluation"]["clauses"]],
            [True, True, True, True, True],
        )


if __name__ == "__main__":
    unittest.main()
