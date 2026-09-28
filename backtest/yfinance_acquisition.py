"""Yahoo acquisition finalization that delegates canonicalization to datasets.py."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from backtest.datasets import checksum, import_dataset, write_manifest
from backtest.reconciliation import validate_acquisition_config

ACTION_COLUMNS = ("Dividends", "Stock Splits", "Capital Gains")


def _read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames or []
    if not rows:
        raise ValueError(f"provider returned no rows: {path}")
    return fields, rows


def _action_summary(fields, rows):
    present = [name for name in ACTION_COLUMNS if name in fields]
    counts = {}
    for name in ACTION_COLUMNS:
        counts[name] = sum(float(row.get(name) or 0) != 0 for row in rows) if name in fields else 0
    return {"columns_present": present, "event_counts": counts}


def _relative(path, root):
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve())).replace("\\", "/")
    except ValueError:
        return str(Path(path).resolve())


def finalize_acquisition(config, *, root, downloaded_at=None):
    """Register downloaded provider files and invoke the existing canonical importer."""
    validate_acquisition_config(config)
    root = Path(root)
    raw_profile = config["profiles"]["raw"]
    adjusted_profile = config["profiles"]["auto_adjusted"]
    raw_path = root / raw_profile["artifact_path"]
    adjusted_path = root / adjusted_profile["artifact_path"]
    raw_fields, raw_rows = _read_csv(raw_path)
    adjusted_fields, adjusted_rows = _read_csv(adjusted_path)
    required = set(config["canonical_column_mapping"].values())
    if not required <= set(raw_fields) or not required <= set(adjusted_fields):
        raise ValueError("provider artifacts do not contain canonical OHLCV source columns")
    if not {"Dividends", "Stock Splits"} <= set(raw_fields):
        raise ValueError("raw provider evidence must preserve Dividends and Stock Splits")
    timestamp_column = config["canonical_column_mapping"]["timestamp"]
    raw_dates = [row[timestamp_column] for row in raw_rows]
    adjusted_dates = [row[timestamp_column] for row in adjusted_rows]
    if raw_dates != adjusted_dates:
        raise ValueError("raw and adjusted provider views must share identical session dates")

    request_parameters = dict(config["common_parameters"])
    request_parameters["period"] = config["download_semantics"]["period"]
    action_summary = _action_summary(raw_fields, raw_rows)
    acquisition_manifest_path = root / config["acquisition_manifest_path"]
    acquisition_manifest = {
        "manifest_version": "1",
        "acquisition_id": config["acquisition_id"],
        "provider": config["provider"],
        "library": config["library"],
        "library_version": config["library_version"],
        "function": config["function"],
        "ticker": config["symbol"],
        "requested_start": config["start"],
        "requested_end_exclusive": config["end_exclusive"],
        "actual_start": raw_dates[0],
        "actual_end": raw_dates[-1],
        "interval": request_parameters["interval"],
        "download_timestamp": downloaded_at or datetime.now(timezone.utc).isoformat(),
        "request_profiles": {
            name: {**request_parameters, "auto_adjust": profile["auto_adjust"]}
            for name, profile in config["profiles"].items()
        },
        "provider_artifacts": {
            "raw": {"path": _relative(raw_path, root), "sha256": checksum(raw_path)},
            "auto_adjusted": {"path": _relative(adjusted_path, root), "sha256": checksum(adjusted_path)},
        },
        "corporate_actions": action_summary,
    }
    acquisition_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if acquisition_manifest_path.exists():
        existing = json.loads(acquisition_manifest_path.read_text(encoding="utf-8"))
        for name in ("raw", "auto_adjusted"):
            if existing["provider_artifacts"][name]["sha256"] != acquisition_manifest["provider_artifacts"][name]["sha256"]:
                raise FileExistsError("immutable acquisition identity already exists with different content")
        acquisition_manifest = existing
    else:
        write_manifest(acquisition_manifest_path, acquisition_manifest)

    shared_provenance = {
        "provider_acquisition_id": config["acquisition_id"],
        "provider_acquisition_manifest": _relative(acquisition_manifest_path, root),
        "provider_raw_artifact": _relative(raw_path, root),
        "provider_raw_sha256": checksum(raw_path),
    }
    results = {}
    for name, path, profile in (
            ("raw", raw_path, raw_profile),
            ("auto_adjusted", adjusted_path, adjusted_profile)):
        results[name] = import_dataset(
            path,
            dataset_id=profile["dataset_id"],
            version=profile["dataset_version"],
            symbol=config["symbol"],
            timeframe=config["common_parameters"]["interval"],
            source_timezone=None,
            timestamp_semantics=config["timestamp_semantics"],
            source=f"{config['provider']} via {config['function']} {config['library_version']}",
            price_adjustment=profile["price_adjustment"],
            adjustment_method=profile["adjustment_method"],
            column_mapping=config["canonical_column_mapping"],
            session_policy=config["session_policy"],
            asset_class=config["asset_class"],
            country=config["country"],
            output_root=root / "data",
            provenance={**shared_provenance, "provider_view": name,
                        "provider_artifact_sha256": checksum(path)},
        )
    return {"acquisition_manifest_path": acquisition_manifest_path,
            "acquisition_manifest": acquisition_manifest, **results}
