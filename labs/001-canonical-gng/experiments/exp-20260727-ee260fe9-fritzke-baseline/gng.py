"""Transparent, dependency-free implementation of Fritzke's original GNG.

The update order follows the 1994 NeurIPS paper rather than later restatements:
age existing winner edges, accumulate pre-adaptation squared error, adapt the
winner and its existing graph neighbours, create or refresh the competitive
Hebbian edge, prune, insert when due, then decay every node error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


Vector = Tuple[float, ...]
Edge = Tuple[int, int]


@dataclass(frozen=True)
class GNGParameters:
    """Constant GNG parameters.

    The learning defaults reproduce the parameter example reported for Figure
    2 of the original paper. ``max_nodes`` is a local growth cap, not a paper
    parameter or universal default.
    """

    insertion_interval: int = 100
    winner_learning_rate: float = 0.2
    neighbor_learning_rate: float = 0.006
    error_reduction: float = 0.5
    max_edge_age: int = 50
    error_decay: float = 0.995
    max_nodes: int = 100

    def __post_init__(self) -> None:
        if self.insertion_interval < 1:
            raise ValueError("insertion_interval must be at least 1")
        if self.max_edge_age < 0:
            raise ValueError("max_edge_age must be non-negative")
        if self.max_nodes < 2:
            raise ValueError("max_nodes must be at least 2")
        for name, value in (
            ("winner_learning_rate", self.winner_learning_rate),
            ("neighbor_learning_rate", self.neighbor_learning_rate),
            ("error_reduction", self.error_reduction),
            ("error_decay", self.error_decay),
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and between 0 and 1")


@dataclass
class Node:
    vector: List[float]
    error: float = 0.0


@dataclass(frozen=True)
class StepResult:
    winner: int
    runner_up: int
    added_edges: Tuple[Edge, ...]
    removed_edges: Tuple[Edge, ...]
    removed_nodes: Tuple[int, ...]
    inserted_node: Optional[int]


class GrowingNeuralGas:
    """A small reference engine intended for inspection and conformance tests."""

    def __init__(
        self,
        initial_vectors: Iterable[Sequence[float]],
        parameters: Optional[GNGParameters] = None,
    ) -> None:
        vectors = [self._coerce_initial_vector(value) for value in initial_vectors]
        if len(vectors) != 2:
            raise ValueError("GNG must start with exactly two vectors")
        if len(vectors[0]) != len(vectors[1]):
            raise ValueError("initial vectors must have the same dimension")

        self.parameters = parameters or GNGParameters()
        self.dimension = len(vectors[0])
        self._nodes: Dict[int, Node] = {
            0: Node(list(vectors[0])),
            1: Node(list(vectors[1])),
        }
        self._edge_ages: Dict[Edge, int] = {}
        self._next_node_id = 2
        self.samples_seen = 0

    @staticmethod
    def _coerce_initial_vector(value: Sequence[float]) -> Vector:
        try:
            vector = tuple(float(component) for component in value)
        except (TypeError, ValueError) as error:
            raise ValueError("vectors must contain finite numeric values") from error
        if not vector or any(not math.isfinite(component) for component in vector):
            raise ValueError("vectors must be non-empty and finite")
        return vector

    def _coerce_signal(self, value: Sequence[float]) -> Vector:
        vector = self._coerce_initial_vector(value)
        if len(vector) != self.dimension:
            raise ValueError(
                f"expected a {self.dimension}-dimensional signal, got {len(vector)}"
            )
        return vector

    @staticmethod
    def _edge(left: int, right: int) -> Edge:
        if left == right:
            raise ValueError("self-edges are not allowed")
        return (left, right) if left < right else (right, left)

    @staticmethod
    def _squared_distance(left: Sequence[float], right: Sequence[float]) -> float:
        return sum((a - b) ** 2 for a, b in zip(left, right))

    @property
    def node_vectors(self) -> Dict[int, Vector]:
        return {
            node_id: tuple(node.vector)
            for node_id, node in sorted(self._nodes.items())
        }

    @property
    def node_errors(self) -> Dict[int, float]:
        return {
            node_id: node.error for node_id, node in sorted(self._nodes.items())
        }

    @property
    def edge_ages(self) -> Dict[Edge, int]:
        return dict(sorted(self._edge_ages.items()))

    def neighbors(self, node_id: int) -> Tuple[int, ...]:
        if node_id not in self._nodes:
            raise KeyError(node_id)
        adjacent = []
        for left, right in self._edge_ages:
            if left == node_id:
                adjacent.append(right)
            elif right == node_id:
                adjacent.append(left)
        return tuple(sorted(adjacent))

    def isolated_nodes(self) -> Tuple[int, ...]:
        return tuple(
            node_id
            for node_id in sorted(self._nodes)
            if not self.neighbors(node_id)
        )

    def _nearest_two_with_distances(
        self, signal: Sequence[float]
    ) -> Tuple[int, int, float, float]:
        vector = self._coerce_signal(signal)
        ranked = sorted(
            (
                (self._squared_distance(node.vector, vector), node_id)
                for node_id, node in self._nodes.items()
            ),
            key=lambda item: (item[0], item[1]),
        )
        first_distance, first = ranked[0]
        second_distance, second = ranked[1]
        return first, second, first_distance, second_distance

    def nearest_two(self, signal: Sequence[float]) -> Tuple[int, int]:
        first, second, _, _ = self._nearest_two_with_distances(signal)
        return first, second

    @staticmethod
    def _move_towards(
        vector: List[float], signal: Sequence[float], learning_rate: float
    ) -> None:
        for index, target in enumerate(signal):
            vector[index] += learning_rate * (target - vector[index])

    def _prune_old_edges(self) -> Tuple[Tuple[Edge, ...], Tuple[int, ...]]:
        expired = tuple(
            edge
            for edge, age in sorted(self._edge_ages.items())
            if age > self.parameters.max_edge_age
        )
        if not expired:
            return (), ()

        candidates = set()
        for edge in expired:
            candidates.update(edge)
            del self._edge_ages[edge]

        removed_nodes = []
        for node_id in sorted(candidates):
            if node_id in self._nodes and not self.neighbors(node_id):
                del self._nodes[node_id]
                removed_nodes.append(node_id)
        return expired, tuple(removed_nodes)

    def _insert_node(self) -> Tuple[int, Tuple[Edge, ...], Tuple[Edge, ...]]:
        q = max(
            self._nodes,
            key=lambda node_id: (self._nodes[node_id].error, -node_id),
        )
        q_neighbors = self.neighbors(q)
        if not q_neighbors:
            raise RuntimeError("maximum-error node has no graph neighbor")
        f = max(
            q_neighbors,
            key=lambda node_id: (self._nodes[node_id].error, -node_id),
        )

        q_node = self._nodes[q]
        f_node = self._nodes[f]
        node_id = self._next_node_id
        self._next_node_id += 1
        midpoint = [
            0.5 * (left + right)
            for left, right in zip(q_node.vector, f_node.vector)
        ]

        old_edge = self._edge(q, f)
        del self._edge_ages[old_edge]
        q_node.error *= self.parameters.error_reduction
        f_node.error *= self.parameters.error_reduction
        self._nodes[node_id] = Node(midpoint, q_node.error)

        first_edge = self._edge(q, node_id)
        second_edge = self._edge(node_id, f)
        self._edge_ages[first_edge] = 0
        self._edge_ages[second_edge] = 0
        return node_id, (first_edge, second_edge), (old_edge,)

    def step(self, signal: Sequence[float]) -> StepResult:
        """Apply one input signal in the exact original-paper event order."""

        vector = self._coerce_signal(signal)
        winner, runner_up, winner_distance, _ = self._nearest_two_with_distances(
            vector
        )

        for edge in tuple(self._edge_ages):
            if winner in edge:
                self._edge_ages[edge] += 1

        winner_node = self._nodes[winner]
        winner_node.error += winner_distance

        existing_neighbors = self.neighbors(winner)
        self._move_towards(
            winner_node.vector,
            vector,
            self.parameters.winner_learning_rate,
        )
        for node_id in existing_neighbors:
            self._move_towards(
                self._nodes[node_id].vector,
                vector,
                self.parameters.neighbor_learning_rate,
            )

        competitive_edge = self._edge(winner, runner_up)
        edge_was_new = competitive_edge not in self._edge_ages
        self._edge_ages[competitive_edge] = 0
        added_edges: List[Edge] = [competitive_edge] if edge_was_new else []

        removed_edges, removed_nodes = self._prune_old_edges()
        all_removed_edges = list(removed_edges)

        self.samples_seen += 1
        inserted_node: Optional[int] = None
        if (
            self.samples_seen % self.parameters.insertion_interval == 0
            and len(self._nodes) < self.parameters.max_nodes
        ):
            inserted_node, insertion_edges, replaced_edges = self._insert_node()
            added_edges.extend(insertion_edges)
            all_removed_edges.extend(replaced_edges)

        for node in self._nodes.values():
            node.error *= self.parameters.error_decay

        self.assert_invariants()
        return StepResult(
            winner=winner,
            runner_up=runner_up,
            added_edges=tuple(added_edges),
            removed_edges=tuple(all_removed_edges),
            removed_nodes=removed_nodes,
            inserted_node=inserted_node,
        )

    def fit(self, signals: Iterable[Sequence[float]]) -> List[StepResult]:
        return [self.step(signal) for signal in signals]

    def mean_squared_quantization_error(
        self, signals: Iterable[Sequence[float]]
    ) -> float:
        distances = []
        for signal in signals:
            _, _, nearest_distance, _ = self._nearest_two_with_distances(signal)
            distances.append(nearest_distance)
        if not distances:
            raise ValueError("at least one signal is required")
        return sum(distances) / len(distances)

    def topographic_error(self, signals: Iterable[Sequence[float]]) -> float:
        misses = 0
        count = 0
        for signal in signals:
            first, second = self.nearest_two(signal)
            count += 1
            if self._edge(first, second) not in self._edge_ages:
                misses += 1
        if count == 0:
            raise ValueError("at least one signal is required")
        return misses / count

    def connected_components(self) -> Tuple[Tuple[int, ...], ...]:
        remaining = set(self._nodes)
        components = []
        while remaining:
            start = min(remaining)
            stack = [start]
            component = set()
            while stack:
                node_id = stack.pop()
                if node_id in component:
                    continue
                component.add(node_id)
                stack.extend(self.neighbors(node_id))
            remaining.difference_update(component)
            components.append(tuple(sorted(component)))
        return tuple(components)

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
        if self.samples_seen and self.isolated_nodes():
            raise AssertionError("processed graphs must not contain isolated nodes")
