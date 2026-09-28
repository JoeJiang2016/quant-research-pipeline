"""Phase 2A deterministic historical dataset loading, validation, and manifests."""
import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume", "symbol")
ADJUSTMENTS = {"raw", "split_adjusted", "total_return_adjusted", "unknown"}


def _timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone offset")
    return parsed


def validate_bars(rows, *, symbol, timeframe):
    """Fail fast on data quality errors; never repair input data silently."""
    if not timeframe:
        raise ValueError("timeframe metadata is required")
    if not symbol:
        raise ValueError("symbol metadata is required")
    bars, previous = [], None
    for index, row in enumerate(rows, start=1):
        try:
            stamp = _timestamp(row["timestamp"])
            values = {key: float(row[key]) for key in REQUIRED_COLUMNS[1:6]}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"row {index}: malformed timestamp or numeric value") from exc
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError(f"row {index}: NaN or infinity is prohibited")
        if str(row.get("symbol", "")) != symbol:
            raise ValueError(f"row {index}: symbol differs from dataset symbol")
        if previous is not None and stamp <= previous:
            raise ValueError(f"row {index}: duplicate or non-monotonic timestamp")
        if values["volume"] < 0 or min(values["open"], values["high"], values["low"], values["close"]) <= 0:
            raise ValueError(f"row {index}: invalid price or volume")
        if values["high"] < max(values["open"], values["close"], values["low"]) or values["low"] > min(values["open"], values["close"], values["high"]):
            raise ValueError(f"row {index}: invalid OHLC relationship")
        bars.append({"timestamp": row["timestamp"], **values, "symbol": symbol})
        previous = stamp
    if not bars:
        raise ValueError("dataset has no bars")
    return bars


def load_dataset(path, *, symbol, timeframe):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    elif path.suffix.lower() in {".parquet", ".pq"}:
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError("Parquet support requires optional pandas/pyarrow dependencies") from exc
        rows = pd.read_parquet(path).to_dict("records")
    else:
        raise ValueError("supported dataset formats are CSV and Parquet")
    if not rows or set(rows[0]) != set(REQUIRED_COLUMNS):
        raise ValueError("dataset must contain exactly timestamp,open,high,low,close,volume,symbol")
    return validate_bars(rows, symbol=symbol, timeframe=timeframe)


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def missing_bar_gaps(bars, expected_seconds):
    """Report gaps only; gap interpretation stays explicit and never changes bars."""
    if not expected_seconds:
        return []
    stamps = [_timestamp(bar["timestamp"]) for bar in bars]
    return [{"after": bars[i - 1]["timestamp"], "before": bars[i]["timestamp"], "seconds": (stamps[i] - stamps[i - 1]).total_seconds()}
            for i in range(1, len(stamps)) if (stamps[i] - stamps[i - 1]).total_seconds() > expected_seconds]


def create_manifest(path, *, dataset_id, symbol, timeframe, timezone, source, price_adjustment="unknown", version="1"):
    if price_adjustment not in ADJUSTMENTS:
        raise ValueError("unknown price adjustment status")
    bars = load_dataset(path, symbol=symbol, timeframe=timeframe)
    return {"dataset_id": dataset_id, "version": version, "symbol": symbol, "timeframe": timeframe,
            "timezone": timezone, "source": source, "price_adjustment": price_adjustment,
            "start": bars[0]["timestamp"], "end": bars[-1]["timestamp"], "rows": len(bars),
            "sha256": checksum(path)}


def write_manifest(path, manifest):
    Path(path).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
