from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPOSITORY_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from atmai_gng import GNGParameters, GrowingNeuralGas, StepResult


FROZEN_MODULE_PATH = (
    REPOSITORY_ROOT
    / "labs"
    / "001-canonical-gng"
    / "experiments"
    / "exp-20260727-ee260fe9-fritzke-baseline"
    / "gng.py"
)
PROMOTED_MODULE_PATH = SRC_ROOT / "atmai_gng" / "gng.py"
BASELINE_RESULT_PATH = FROZEN_MODULE_PATH.parent / "results" / "baseline.json"
FROZEN_SHA256 = (
    "e684e68c0e87a7664e7c5294647f3c09cdb939775e2d322321268b5c56d7ee10"
)
FROZEN_SPEC = importlib.util.spec_from_file_location(
    "frozen_fritzke_baseline_gng",
    FROZEN_MODULE_PATH,
)
if FROZEN_SPEC is None or FROZEN_SPEC.loader is None:
    raise ImportError(f"could not load frozen GNG module from {FROZEN_MODULE_PATH}")
FROZEN_GNG = importlib.util.module_from_spec(FROZEN_SPEC)
sys.modules[FROZEN_SPEC.name] = FROZEN_GNG
FROZEN_SPEC.loader.exec_module(FROZEN_GNG)


class PromotedGNGTests(unittest.TestCase):
    def test_public_interface_is_explicit(self) -> None:
        self.assertEqual(
            sys.modules["atmai_gng"].__all__,
            ["GNGParameters", "GrowingNeuralGas", "StepResult"],
        )
        self.assertTrue(isinstance(GNGParameters(), GNGParameters))
        self.assertTrue(issubclass(StepResult, object))

    def test_promoted_source_matches_the_frozen_evidence_record(self) -> None:
        baseline_report = json.loads(BASELINE_RESULT_PATH.read_text(encoding="utf-8"))
        recorded_digest = baseline_report["source_sha256"]["gng.py"]
        frozen_digest = hashlib.sha256(FROZEN_MODULE_PATH.read_bytes()).hexdigest()
        promoted_digest = hashlib.sha256(PROMOTED_MODULE_PATH.read_bytes()).hexdigest()

        self.assertEqual(recorded_digest, FROZEN_SHA256)
        self.assertEqual(frozen_digest, recorded_digest)
        self.assertEqual(promoted_digest, recorded_digest)

    def test_promoted_engine_matches_frozen_baseline_step_by_step(self) -> None:
        parameters = GNGParameters(
            insertion_interval=17,
            winner_learning_rate=0.2,
            neighbor_learning_rate=0.006,
            error_reduction=0.5,
            max_edge_age=23,
            error_decay=0.995,
            max_nodes=24,
        )
        frozen_parameters = FROZEN_GNG.GNGParameters(
            insertion_interval=17,
            winner_learning_rate=0.2,
            neighbor_learning_rate=0.006,
            error_reduction=0.5,
            max_edge_age=23,
            error_decay=0.995,
            max_nodes=24,
        )
        initial_vectors = [(-0.75, -0.25), (0.75, 0.25)]
        promoted = GrowingNeuralGas(initial_vectors, parameters)
        frozen = FROZEN_GNG.GrowingNeuralGas(initial_vectors, frozen_parameters)
        generator = random.Random(20260727)

        for _ in range(250):
            signal = (
                generator.uniform(-1.0, 1.0),
                generator.gauss(0.0, 0.4),
            )
            promoted_result = promoted.step(signal)
            frozen_result = frozen.step(signal)

            self.assertEqual(
                (
                    promoted_result.winner,
                    promoted_result.runner_up,
                    promoted_result.added_edges,
                    promoted_result.removed_edges,
                    promoted_result.removed_nodes,
                    promoted_result.inserted_node,
                ),
                (
                    frozen_result.winner,
                    frozen_result.runner_up,
                    frozen_result.added_edges,
                    frozen_result.removed_edges,
                    frozen_result.removed_nodes,
                    frozen_result.inserted_node,
                ),
            )
            self.assertEqual(promoted.node_vectors, frozen.node_vectors)
            self.assertEqual(promoted.node_errors, frozen.node_errors)
            self.assertEqual(promoted.edge_ages, frozen.edge_ages)
            self.assertEqual(promoted.samples_seen, frozen.samples_seen)

        self.assertEqual(promoted.connected_components(), frozen.connected_components())
        self.assertEqual(promoted.isolated_nodes(), frozen.isolated_nodes())
        self.assertIsNone(promoted.assert_invariants())


if __name__ == "__main__":
    unittest.main()
