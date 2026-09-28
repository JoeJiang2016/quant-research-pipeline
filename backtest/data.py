"""Strict, deterministic OHLCV loading and identity helpers."""
import csv
import hashlib
from datetime import datetime

REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def load_bars(path):
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or list(rows[0]) != REQUIRED_COLUMNS:
        raise ValueError("OHLCV must contain exactly timestamp,open,high,low,close,volume in that order")
    bars = []
    previous = None
    for row in rows:
        try:
            timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            bar = {key: float(row[key]) for key in REQUIRED_COLUMNS[1:]}
        except (TypeError, ValueError) as exc:
            raise ValueError("OHLCV contains malformed timestamps, missing, or nonnumeric values") from exc
        if previous is not None and timestamp <= previous:
            raise ValueError("OHLCV timestamps must be strictly increasing")
        if min(bar["open"], bar["high"], bar["low"], bar["close"]) <= 0 or bar["high"] < max(bar["open"], bar["close"]) or bar["low"] > min(bar["open"], bar["close"]) or bar["volume"] < 0:
            raise ValueError("OHLCV contains invalid price or volume relationships")
        bars.append({"timestamp": row["timestamp"], **bar})
        previous = timestamp
    return bars


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
