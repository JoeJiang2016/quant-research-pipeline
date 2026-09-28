"""Deterministic session-date comparison for controlled market-data reconciliation."""
import csv
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

IMPORTANT_PARAMETERS = {
    "interval", "back_adjust", "actions", "prepost", "repair", "progress",
    "threads", "multi_level_index", "ignore_tz", "group_by", "keepna",
    "rounding", "timeout",
}
PROFILES = {"raw", "auto_adjusted"}


def validate_acquisition_config(config, *, installed_yfinance_version=None):
    required = {"contract_version", "acquisition_id", "provider", "library", "library_version", "function", "cache_path", "symbol",
                "start", "end_exclusive", "timestamp_semantics",
                "download_semantics", "common_parameters", "profiles",
                "acquisition_manifest_path", "canonical_column_mapping",
                "session_policy", "asset_class", "country"}
    missing = required - set(config)
    if missing:
        raise ValueError(f"acquisition config missing: {sorted(missing)}")
    parameter_missing = IMPORTANT_PARAMETERS - set(config["common_parameters"])
    if parameter_missing:
        raise ValueError(f"download parameters must be explicit: {sorted(parameter_missing)}")
    if set(config["profiles"]) != PROFILES:
        raise ValueError("raw and auto_adjusted profiles are required")
    profile_required = {"auto_adjust", "dataset_id", "dataset_version", "artifact_path",
                        "price_adjustment", "adjustment_method"}
    for name, profile in config["profiles"].items():
        missing_profile = profile_required - set(profile)
        if missing_profile:
            raise ValueError(f"{name} profile missing: {sorted(missing_profile)}")
    if config["profiles"]["raw"].get("auto_adjust") is not False:
        raise ValueError("raw profile must set auto_adjust=false")
    if config["profiles"]["auto_adjusted"].get("auto_adjust") is not True:
        raise ValueError("auto_adjusted profile must set auto_adjust=true")
    if config["timestamp_semantics"] != "session_date":
        raise ValueError("daily reconciliation must use session_date")
    if config["common_parameters"]["repair"] is not False:
        raise ValueError("canonical acquisition must set repair=false")
    if config["common_parameters"]["actions"] is not True:
        raise ValueError("canonical acquisition must preserve actions")
    if not config["asset_class"] or config["asset_class"] == "unknown":
        raise ValueError("canonical acquisition requires explicit asset_class")
    if not re.fullmatch(r"[A-Z]{2}", config["country"]):
        raise ValueError("canonical acquisition requires ISO alpha-2 country")
    if config["profiles"]["raw"]["dataset_id"] == config["profiles"]["auto_adjusted"]["dataset_id"]:
        raise ValueError("raw and adjusted dataset identities must differ")
    if config["download_semantics"] != {
            "start_inclusive": True, "end_exclusive": True, "period": None}:
        raise ValueError("start/end semantics must be explicit")
    if installed_yfinance_version and config["library_version"] != installed_yfinance_version:
        raise ValueError("installed yfinance version differs from acquisition contract")
    return config


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_session_rows(path, *, date_column="Date"):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or date_column not in reader.fieldnames:
            raise ValueError(f"missing session-date column: {date_column}")
        rows = {}
        for row in reader:
            session = row[date_column]
            if len(session) != 10 or session[4] != "-" or session[7] != "-":
                raise ValueError(f"invalid session date: {session}")
            if session in rows:
                raise ValueError(f"duplicate session date: {session}")
            rows[session] = row
    return rows


def _decimal(value, *, field, session):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"nonnumeric {field} at {session}") from exc


def compare_session_rows(left, right, *, fields, absolute_tolerance,
                         relative_tolerance, mismatch_example_limit=10):
    absolute_tolerance = Decimal(str(absolute_tolerance))
    relative_tolerance = Decimal(str(relative_tolerance))
    common = sorted(set(left) & set(right))
    metrics = {}
    mismatch_examples = []
    for field in fields:
        exact = tolerance = 0
        field_examples = 0
        maximum_absolute = Decimal(0)
        maximum_relative = Decimal(0)
        for session in common:
            left_value = _decimal(left[session].get(field), field=field, session=session)
            right_value = _decimal(right[session].get(field), field=field, session=session)
            difference = abs(left_value - right_value)
            denominator = max(abs(left_value), abs(right_value))
            relative = difference / denominator if denominator else Decimal(0)
            maximum_absolute = max(maximum_absolute, difference)
            maximum_relative = max(maximum_relative, relative)
            if left_value == right_value:
                exact += 1
            threshold = absolute_tolerance + relative_tolerance * denominator
            if difference <= threshold:
                tolerance += 1
            elif field_examples < mismatch_example_limit:
                mismatch_examples.append({
                    "session_date": session, "field": field,
                    "legacy": str(left_value), "candidate": str(right_value),
                    "absolute_difference": str(difference),
                    "relative_difference": str(relative),
                })
                field_examples += 1
        metrics[field] = {
            "exact_match_count": exact,
            "tolerance_match_count": tolerance,
            "mismatch_count": len(common) - tolerance,
            "max_absolute_difference": str(maximum_absolute),
            "max_relative_difference": str(maximum_relative),
        }
    total_mismatches = sum(item["mismatch_count"] for item in metrics.values())
    return {
        "overlap_row_count": len(common),
        "left_only_dates": sorted(set(left) - set(right)),
        "right_only_dates": sorted(set(right) - set(left)),
        "fields": metrics,
        "total_field_mismatches": total_mismatches,
        "mismatch_examples": mismatch_examples,
        "mismatch_examples_truncated": total_mismatches > len(mismatch_examples),
        "absolute_tolerance": str(absolute_tolerance),
        "relative_tolerance": str(relative_tolerance),
    }


def compare_csv_files(left_path, right_path, *, fields, absolute_tolerance,
                      relative_tolerance):
    return compare_session_rows(
        load_session_rows(left_path), load_session_rows(right_path), fields=fields,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_acquisition_config(config)
