from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPOSITORY_ROOT
    / "labs"
    / "001-canonical-gng"
    / "experiments"
    / "exp-20260727-ee260fe9-fritzke-baseline"
    / "gng.py"
)
RUNNER_PATH = MODULE_PATH.with_name("run.py")
MODULE_NAME = "fritzke_baseline_gng"
MODULE_SPEC = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise ImportError(f"could not load canonical GNG module from {MODULE_PATH}")
GNG = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_NAME] = GNG
MODULE_SPEC.loader.exec_module(GNG)

GNGParameters = GNG.GNGParameters
GrowingNeuralGas = GNG.GrowingNeuralGas


class FritzkeBaselineTests(unittest.TestCase):
    def test_paper_parameter_defaults_are_explicit(self) -> None:
        parameters = GNGParameters()

        self.assertEqual(parameters.insertion_interval, 100)
        self.assertEqual(parameters.winner_learning_rate, 0.2)
        self.assertEqual(parameters.neighbor_learning_rate, 0.006)
        self.assertEqual(parameters.error_reduction, 0.5)
        self.assertEqual(parameters.max_edge_age, 50)
        self.assertEqual(parameters.error_decay, 0.995)
        self.assertEqual(parameters.max_nodes, 100)

    def test_step_uses_pre_update_error_and_only_pre_existing_neighbors(self) -> None:
        model = GrowingNeuralGas(
            [[0.0], [10.0]],
            GNGParameters(
                insertion_interval=100,
                winner_learning_rate=0.5,
                neighbor_learning_rate=0.25,
                error_decay=1.0,
            ),
        )

        first = model.step([4.0])

        self.assertEqual((first.winner, first.runner_up), (0, 1))
        self.assertEqual(first.added_edges, ((0, 1),))
        self.assertEqual(model.node_vectors, {0: (2.0,), 1: (10.0,)})
        self.assertEqual(model.node_errors, {0: 16.0, 1: 0.0})
        self.assertEqual(model.edge_ages, {(0, 1): 0})

        model.step([4.0])

        self.assertEqual(model.node_vectors, {0: (3.0,), 1: (8.5,)})
        self.assertEqual(model.node_errors, {0: 20.0, 1: 0.0})
        self.assertEqual(model.edge_ages, {(0, 1): 0})
        self.assertEqual(model.samples_seen, 2)

    def test_edge_expires_only_above_boundary_then_isolate_is_deleted(self) -> None:
        model = GrowingNeuralGas(
            [[0.0], [10.0]],
            GNGParameters(
                insertion_interval=3,
                winner_learning_rate=0.0,
                neighbor_learning_rate=0.0,
                error_reduction=0.5,
                max_edge_age=1,
                error_decay=1.0,
                max_nodes=3,
            ),
        )
        model.step([4.0])
        model.step([4.0])
        insertion = model.step([4.0])
        self.assertEqual(insertion.inserted_node, 2)
        self.assertEqual(model.edge_ages, {(0, 2): 0, (1, 2): 0})

        at_boundary = model.step([5.0])

        self.assertEqual(at_boundary.removed_edges, ())
        self.assertEqual(at_boundary.removed_nodes, ())
        self.assertEqual(model.edge_ages, {(0, 2): 0, (1, 2): 1})
        self.assertEqual(model.node_vectors, {0: (0.0,), 1: (10.0,), 2: (5.0,)})

        expired = model.step([5.0])

        self.assertEqual(expired.removed_edges, ((1, 2),))
        self.assertEqual(expired.removed_nodes, (1,))
        self.assertEqual(model.node_vectors, {0: (0.0,), 2: (5.0,)})
        self.assertEqual(model.edge_ages, {(0, 2): 0})
        self.assertEqual(model.connected_components(), ((0, 2),))
        self.assertIsNone(model.assert_invariants())

    def test_insertion_replaces_edge_and_copies_scaled_q_error_before_decay(
        self,
    ) -> None:
        model = GrowingNeuralGas(
            [[0.0], [10.0]],
            GNGParameters(
                insertion_interval=1,
                winner_learning_rate=0.0,
                neighbor_learning_rate=0.0,
                error_reduction=0.5,
                error_decay=0.9,
                max_nodes=3,
            ),
        )

        result = model.step([4.0])

        self.assertEqual(result.inserted_node, 2)
        self.assertEqual(
            result.added_edges,
            ((0, 1), (0, 2), (1, 2)),
        )
        self.assertEqual(result.removed_edges, ((0, 1),))
        self.assertEqual(model.node_vectors, {0: (0.0,), 1: (10.0,), 2: (5.0,)})
        self.assertEqual(model.edge_ages, {(0, 2): 0, (1, 2): 0})
        self.assertAlmostEqual(model.node_errors[0], 7.2)
        self.assertAlmostEqual(model.node_errors[1], 0.0)
        self.assertAlmostEqual(model.node_errors[2], 7.2)
        self.assertIsNone(model.assert_invariants())

    def test_equal_distance_ties_are_broken_by_node_id(self) -> None:
        model = GrowingNeuralGas(
            [[-1.0], [1.0]],
            GNGParameters(
                insertion_interval=100,
                winner_learning_rate=0.0,
                neighbor_learning_rate=0.0,
                error_decay=1.0,
            ),
        )

        self.assertEqual(model.nearest_two([0.0]), (0, 1))
        self.assertEqual(model.nearest_two([0.0]), (0, 1))

        result = model.step([0.0])

        self.assertEqual((result.winner, result.runner_up), (0, 1))
        self.assertEqual(model.node_errors, {0: 1.0, 1: 0.0})

    def test_metric_fixture_has_exact_quantization_and_topographic_errors(
        self,
    ) -> None:
        model = GrowingNeuralGas(
            [[0.0, 0.0], [4.0, 0.0]],
            GNGParameters(
                insertion_interval=100,
                winner_learning_rate=0.0,
                neighbor_learning_rate=0.0,
                error_decay=1.0,
            ),
        )
        samples = [[0.0, 0.0], [1.0, 0.0], [3.0, 0.0], [4.0, 0.0]]

        self.assertEqual(model.mean_squared_quantization_error(samples), 0.5)
        self.assertEqual(model.topographic_error(samples), 1.0)
        self.assertEqual(model.connected_components(), ((0,), (1,)))

        model.step([0.0, 0.0])

        self.assertEqual(model.mean_squared_quantization_error(samples), 0.5)
        self.assertEqual(model.topographic_error(samples), 0.0)
        self.assertEqual(model.connected_components(), ((0, 1),))
        with self.assertRaises(ValueError):
            model.mean_squared_quantization_error([])
        with self.assertRaises(ValueError):
            model.topographic_error([])

    def test_stationary_signal_reduces_quantization_error(self) -> None:
        model = GrowingNeuralGas(
            [[0.0], [10.0]],
            GNGParameters(
                insertion_interval=10_000,
                winner_learning_rate=0.2,
                neighbor_learning_rate=0.006,
                error_decay=0.995,
                max_nodes=2,
            ),
        )
        stationary_sample = [[2.0]]
        initial_error = model.mean_squared_quantization_error(stationary_sample)

        model.fit([[2.0]] * 80)

        final_error = model.mean_squared_quantization_error(stationary_sample)
        self.assertLess(final_error, initial_error * 1e-10)
        self.assertAlmostEqual(model.node_vectors[0][0], 2.0, places=6)
        self.assertEqual(model.samples_seen, 80)
        self.assertEqual(model.topographic_error(stationary_sample), 0.0)
        self.assertEqual(model.connected_components(), ((0, 1),))
        self.assertIsNone(model.assert_invariants())

    def test_runner_emits_a_bounded_reproducibility_record(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--steps", "100", "--stdout"],
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(completed.stdout)

        self.assertEqual(report["schema"], "atmai.gng.stationary-baseline/v1")
        self.assertEqual(
            report["protocol"]["dataset_order"],
            [
                "uniform_square",
                "noisy_ring",
                "two_gaussian_blobs",
                "two_moons",
            ],
        )
        self.assertEqual(report["protocol"]["training_steps_per_dataset"], 100)
        self.assertEqual(report["protocol"]["evaluation_checkpoints"], [0, 100])
        self.assertEqual(len(report["datasets"]), 4)
        self.assertEqual(
            set(report["source_sha256"]),
            {"gng.py", "run.py"},
        )
        for digest in report["source_sha256"].values():
            self.assertEqual(len(digest), 64)
        for dataset in report["datasets"]:
            self.assertEqual(dataset["final_graph"]["nodes"], 3)
            self.assertEqual(dataset["final_graph"]["isolates"], 0)
            self.assertEqual(dataset["churn"]["node_insertions"], 1)


if __name__ == "__main__":
    unittest.main()
