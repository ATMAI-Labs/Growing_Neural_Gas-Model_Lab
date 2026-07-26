"""Stable public interface for ATMAI's reference Growing Neural Gas engine."""

from .gng import GNGParameters, GrowingNeuralGas, StepResult

__all__ = ["GNGParameters", "GrowingNeuralGas", "StepResult"]
