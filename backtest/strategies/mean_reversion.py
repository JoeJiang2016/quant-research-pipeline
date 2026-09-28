"""Deterministic rolling z-score signals; no execution or position state."""
import math
from statistics import mean, pstdev

def minimum_history(strategy):
    return max(strategy["entry"]["mean_lookback"], strategy["exit"]["atr_period"])

def _zscore(strategy, bars, index):
    lookback = strategy["entry"]["mean_lookback"]
    if index + 1 < lookback: return None
    closes = [bar["close"] for bar in bars[index-lookback+1:index+1]]
    deviation = pstdev(closes)
    if deviation == 0 or not math.isfinite(deviation): return None
    value = (closes[-1] - mean(closes)) / deviation
    return value if math.isfinite(value) else None

def evaluate_entry(strategy, bars, index):
    value = _zscore(strategy, bars, index)
    return value is not None and value <= -strategy["entry"]["entry_z"]

def evaluate_exit(strategy, bars, index, position):
    value = _zscore(strategy, bars, index)
    return position["side"] == "long" and value is not None and value >= strategy["exit"]["exit_z"]
