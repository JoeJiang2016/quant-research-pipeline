"""Deterministic, boundary-exclusive dataset splitting for research evaluation."""
from enum import Enum


class DatasetSplit(str, Enum):
    IN_SAMPLE = "IN_SAMPLE"
    OUT_OF_SAMPLE = "OUT_OF_SAMPLE"


def split_bars(bars, in_sample_end, out_of_sample_start, split):
    if not in_sample_end or not out_of_sample_start or in_sample_end >= out_of_sample_start:
        raise ValueError("evaluation requires in_sample_end before out_of_sample_start")
    if split == DatasetSplit.IN_SAMPLE:
        return [bar for bar in bars if bar["timestamp"] <= in_sample_end]
    if split == DatasetSplit.OUT_OF_SAMPLE:
        return [bar for bar in bars if bar["timestamp"] >= out_of_sample_start]
    raise ValueError("unknown dataset split")
