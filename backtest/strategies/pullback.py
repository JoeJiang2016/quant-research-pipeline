"""Deterministic trend-pullback entry signals; no order or position state."""


def minimum_history(strategy):
    return max(strategy["entry"]["slow_ema_period"], strategy["exit"]["atr_period"])


def _ema(values, period):
    alpha = 2 / (period + 1)
    value = values[0]
    for current in values[1:]:
        value = alpha * current + (1 - alpha) * value
    return value


def _atr(bars, index, period):
    ranges = []
    for i in range(index - period + 1, index + 1):
        previous_close = bars[i - 1]["close"] if i else bars[i]["close"]
        ranges.append(max(
            bars[i]["high"] - bars[i]["low"],
            abs(bars[i]["high"] - previous_close),
            abs(bars[i]["low"] - previous_close),
        ))
    return sum(ranges) / len(ranges)


def evaluate_entry(strategy, bars, index):
    entry = strategy["entry"]
    if index < minimum_history(strategy) or index == 0:
        return False
    closes = [bar["close"] for bar in bars[:index + 1]]
    fast = _ema(closes, entry["fast_ema_period"])
    slow = _ema(closes, entry["slow_ema_period"])
    previous_fast = _ema(closes[:-1], entry["fast_ema_period"])
    current = bars[index]["close"]
    previous = bars[index - 1]["close"]
    previous_atr = _atr(bars, index - 1, strategy["exit"]["atr_period"])
    trend = fast > slow and current > slow
    pullback = previous_atr > 0 and previous <= previous_fast and abs(previous - previous_fast) / previous_atr <= entry["pullback_distance_atr"]
    confirmation = current > previous and current > fast
    return trend and pullback and confirmation
