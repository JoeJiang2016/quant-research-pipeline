"""Minimal contract for strategy-specific signal logic."""
from typing import Protocol


class StrategySignalLogic(Protocol):
    def minimum_history(self, strategy: dict) -> int: ...
    def evaluate_entry(self, strategy: dict, bars: list[dict], index: int) -> bool: ...
