"""Close-confirmed breakout signals. This module never executes orders."""


def minimum_history(strategy):
    return strategy["entry"]["lookback_bars"]


def evaluate_entry(strategy, bars, index):
    entry = strategy["entry"]
    lookback = entry["lookback_bars"]
    if index < lookback:
        return False
    # The current bar is intentionally excluded from the reference window.
    previous = bars[index - lookback:index]
    if entry["direction"] == "long":
        return bars[index]["close"] > max(bar["high"] for bar in previous)
    return bars[index]["close"] < min(bar["low"] for bar in previous)
