"""Phase 2A deterministic historical dataset loading, validation, and manifests."""
import csv
import hashlib
import json
import math
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume", "symbol")
ADJUSTMENTS = {"raw", "split_adjusted", "total_return_adjusted", "provider_adjusted", "unknown"}
TIMESTAMP_SEMANTICS = {"instant", "session_date"}
SESSION_DATE_TIMEFRAMES = {"1d", "1wk"}
# Absorbs representation noise such as 10.299999999999 vs 10.300000000000
# without accepting materially inconsistent market prices.
OHLC_ABSOLUTE_TOLERANCE = 1e-12


def _timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone offset")
    return parsed


def _session_date(value):
    text = str(value)
    if len(text) != 10 or date.fromisoformat(text).isoformat() != text:
        raise ValueError("session-date timestamps must use YYYY-MM-DD")
    return date.fromisoformat(text)


def _temporal_label(value, *, timeframe, timestamp_semantics):
    if timestamp_semantics not in TIMESTAMP_SEMANTICS:
        raise ValueError(f"unknown timestamp semantics: {timestamp_semantics}")
    if timestamp_semantics == "session_date":
        if timeframe not in SESSION_DATE_TIMEFRAMES:
            raise ValueError("session_date is allowed only for daily or weekly timeframes")
        return _session_date(value)
    return _timestamp(value)


def validate_bars(rows, *, symbol, timeframe, timestamp_semantics="instant"):
    """Fail fast on data quality errors; never repair input data silently."""
    if not timeframe:
        raise ValueError("timeframe metadata is required")
    if not symbol:
        raise ValueError("symbol metadata is required")
    bars, previous = [], None
    for index, row in enumerate(rows, start=1):
        try:
            stamp = _temporal_label(row["timestamp"], timeframe=timeframe,
                                    timestamp_semantics=timestamp_semantics)
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
        if (values["high"] + OHLC_ABSOLUTE_TOLERANCE
                < max(values["open"], values["close"], values["low"]) or
                values["low"] - OHLC_ABSOLUTE_TOLERANCE
                > min(values["open"], values["close"], values["high"])):
            raise ValueError(f"row {index}: invalid OHLC relationship")
        bars.append({"timestamp": row["timestamp"], **values, "symbol": symbol})
        previous = stamp
    if not bars:
        raise ValueError("dataset has no bars")
    return bars


def load_dataset(path, *, symbol, timeframe, timestamp_semantics="instant"):
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
    return validate_bars(rows, symbol=symbol, timeframe=timeframe,
                         timestamp_semantics=timestamp_semantics)


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def missing_bar_gaps(bars, expected_seconds):
    """Report gaps only; gap interpretation stays explicit and never changes bars."""
    if not expected_seconds:
        return []
    stamps = [_timestamp(bar["timestamp"]) for bar in bars]
    return [{"after": bars[i - 1]["timestamp"], "before": bars[i]["timestamp"], "seconds": (stamps[i] - stamps[i - 1]).total_seconds()}
            for i in range(1, len(stamps)) if (stamps[i] - stamps[i - 1]).total_seconds() > expected_seconds]


def create_manifest(path, *, dataset_id, symbol, timeframe, timezone, source,
                    price_adjustment="unknown", version="1", raw_path=None,
                    source_timezone=None, timestamp_semantics="instant",
                    session_policy="unknown", asset_class="unknown",
                    column_mapping=None, quality_summary=None,
                    import_timestamp=None, adjustment_method=None,
                    provenance=None):
    if price_adjustment not in ADJUSTMENTS:
        raise ValueError("unknown price adjustment status")
    bars = load_dataset(path, symbol=symbol, timeframe=timeframe,
                        timestamp_semantics=timestamp_semantics)
    processed_checksum=checksum(path)
    manifest={"dataset_id": dataset_id, "dataset_version": version, "version": version, "symbol": symbol, "asset_class": asset_class, "timeframe": timeframe,
            "timezone": timezone, "timestamp_semantics": timestamp_semantics,
            "source": source, "price_adjustment": price_adjustment,
            "start": bars[0]["timestamp"], "end": bars[-1]["timestamp"], "rows": len(bars),
            "row_count": len(bars), "sha256": processed_checksum, "raw_file_sha256": checksum(raw_path or path),
            "processed_file_sha256": processed_checksum, "source_timezone": source_timezone or timezone,
            "canonical_timezone": timezone, "session_policy": session_policy, "processed_path": str(Path(path)),
            "import_timestamp": import_timestamp or datetime.now(timezone_module.utc).isoformat(),
            "column_mapping": column_mapping or {name:name for name in REQUIRED_COLUMNS},
            "quality_summary": quality_summary or {"rows_validated":len(bars),"large_gaps":[]}}
    if adjustment_method is not None:
        manifest["adjustment_method"] = adjustment_method
    if provenance is not None:
        manifest["provenance"] = provenance
    return manifest


def write_manifest(path, manifest):
    Path(path).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


# Alias avoids shadowing by create_manifest's legacy `timezone` argument.
timezone_module = timezone


def _is_null(value):
    return value is None or str(value).strip() == ""


def _largest_date_gaps(bars, *, timestamp_semantics, limit=10):
    parsed = [(_session_date(bar["timestamp"])
               if timestamp_semantics == "session_date"
               else _timestamp(bar["timestamp"])) for bar in bars]
    gaps = [{"after": bars[index - 1]["timestamp"],
             "before": bars[index]["timestamp"],
             "calendar_days": (parsed[index] - parsed[index - 1]).total_seconds() / 86400}
            for index in range(1, len(parsed))]
    return sorted(gaps, key=lambda item: (-item["calendar_days"], item["after"]))[:limit]


def import_dataset(input_path, *, dataset_id, symbol, timeframe, source_timezone, source,
                   price_adjustment="unknown", version="1", column_mapping=None,
                   session_policy="unknown", asset_class="unknown", output_root=None,
                   expected_gap_seconds=None, timestamp_semantics="instant",
                   adjustment_method=None, provenance=None):
    """Copy immutable raw input and normalize it under explicit timestamp semantics."""
    input_path=Path(input_path); root=Path(output_root or Path(__file__).resolve().parents[1]/"data")
    if not symbol: raise ValueError("explicit symbol metadata is required")
    if timestamp_semantics not in TIMESTAMP_SEMANTICS: raise ValueError("unknown timestamp semantics")
    if timestamp_semantics == "session_date" and timeframe not in SESSION_DATE_TIMEFRAMES:
        raise ValueError("session_date is allowed only for daily or weekly timeframes")
    mapping=column_mapping or {name:name for name in REQUIRED_COLUMNS if name != "symbol"}
    if "timestamp" not in mapping or any(name not in mapping for name in ("open","high","low","close","volume")):
        raise ValueError("explicit mapping must cover timestamp,open,high,low,close,volume")
    raw_dir,processed_dir,manifest_dir=root/"raw",root/"processed",root/"manifests"
    for directory in (raw_dir,processed_dir,manifest_dir): directory.mkdir(parents=True,exist_ok=True)
    raw_path=raw_dir/f"{dataset_id}_v{version}{input_path.suffix.lower()}"
    if raw_path.exists():
        if checksum(raw_path) != checksum(input_path): raise FileExistsError("immutable raw dataset version already exists with different content")
    else: shutil.copy2(input_path,raw_path)
    if input_path.suffix.lower() == ".csv":
        with input_path.open(newline="",encoding="utf-8") as handle: source_rows=list(csv.DictReader(handle))
    elif input_path.suffix.lower() in {".parquet",".pq"}:
        try: import pandas as pd
        except ImportError as exc: raise RuntimeError("Parquet import requires optional pandas/pyarrow dependencies") from exc
        source_rows=pd.read_parquet(input_path).to_dict("records")
    else: raise ValueError("supported import formats are CSV and Parquet")
    normalized=[]
    for index,row in enumerate(source_rows,start=1):
        try:
            source_stamp=row[mapping["timestamp"]]
        except KeyError as exc:
            raise ValueError(f"row {index}: malformed timestamp") from exc
        if timestamp_semantics == "session_date":
            try:
                canonical=_session_date(source_stamp).isoformat()
            except ValueError as exc:
                raise ValueError(f"row {index}: malformed timestamp") from exc
        else:
            try:
                stamp=datetime.fromisoformat(str(source_stamp).replace("Z","+00:00"))
            except ValueError as exc:
                raise ValueError(f"row {index}: malformed timestamp") from exc
            if stamp.tzinfo is None:
                if not source_timezone: raise ValueError("naive timestamps require explicit source timezone")
                stamp=stamp.replace(tzinfo=timezone.utc if source_timezone.upper() in {"UTC","ETC/UTC","Z"} else ZoneInfo(source_timezone))
            canonical=stamp.astimezone(timezone.utc).isoformat().replace("+00:00","Z")
        normalized.append({"timestamp":canonical,**{name:row[mapping[name]] for name in ("open","high","low","close","volume")},"symbol":row[mapping["symbol"]] if "symbol" in mapping else symbol})
    bars=validate_bars(normalized,symbol=symbol,timeframe=timeframe,
                       timestamp_semantics=timestamp_semantics)
    processed_path=processed_dir/f"{dataset_id}_v{version}.csv"
    with processed_path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=REQUIRED_COLUMNS,lineterminator="\n"); writer.writeheader(); writer.writerows(bars)
    source_nulls=sum(_is_null(value) for row in source_rows for value in row.values())
    canonical_nulls=sum(_is_null(row.get(mapping[name])) for row in source_rows
                        for name in ("timestamp","open","high","low","close","volume"))
    quality={"rows_validated":len(bars),"row_count":len(bars),
             "first":bars[0]["timestamp"],"last":bars[-1]["timestamp"],
             "source_null_count":source_nulls,"canonical_null_count":canonical_nulls,
             "malformed_rows":0,"duplicate_timestamps":0,"invalid_ohlc":0,
             "negative_volume":0,"nan_or_infinity":0,"strictly_increasing":True,
             "large_gaps":missing_bar_gaps(bars,expected_gap_seconds)
                 if timestamp_semantics == "instant" else [],
             "largest_date_gaps":_largest_date_gaps(
                 bars,timestamp_semantics=timestamp_semantics),
             "gap_interpretation":"informational_only_no_exchange_calendar"}
    canonical_timezone=None if timestamp_semantics == "session_date" else "UTC"
    manifest=create_manifest(processed_path,dataset_id=dataset_id,symbol=symbol,timeframe=timeframe,timezone=canonical_timezone,source=source,price_adjustment=price_adjustment,version=version,raw_path=raw_path,source_timezone=source_timezone,timestamp_semantics=timestamp_semantics,session_policy=session_policy,asset_class=asset_class,column_mapping=mapping,quality_summary=quality,adjustment_method=adjustment_method,provenance=provenance)
    manifest_path=manifest_dir/f"{dataset_id}_v{version}.json"; write_manifest(manifest_path,manifest)
    quality_path=manifest_dir/f"{dataset_id}_v{version}.quality.json"; quality_path.write_text(json.dumps(quality,indent=2)+"\n",encoding="utf-8")
    return {"raw_path":raw_path,"processed_path":processed_path,"manifest_path":manifest_path,"quality_path":quality_path,"manifest":manifest}
