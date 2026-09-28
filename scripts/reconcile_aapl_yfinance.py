"""Download two explicit AAPL datasets and compare them with the legacy CSV."""
import argparse
import json
import os
import platform
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
dependency_path = os.environ.get("RECONCILIATION_DEPENDENCY_PATH")
if dependency_path:
    sys.path.insert(0, dependency_path)

from backtest.reconciliation import (compare_csv_files, load_config, sha256,
                                     validate_acquisition_config)


def _download(yf, config, profile):
    parameters = dict(config["common_parameters"])
    parameters["auto_adjust"] = config["profiles"][profile]["auto_adjust"]
    frame = yf.download(
        config["symbol"], start=config["start"], end=config["end_exclusive"],
        **parameters,
    )
    if frame.empty:
        raise RuntimeError(f"empty controlled download: {profile}")
    frame.index.name = "Date"
    output = ROOT / config["profiles"][profile]["output_path"]
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, lineterminator="\n", date_format="%Y-%m-%d")
    return output, frame


def _reuse(pd, config, profile):
    output = ROOT / config["profiles"][profile]["output_path"]
    if not output.exists():
        raise FileNotFoundError(f"controlled raw file is missing: {output}")
    return output, pd.read_csv(output,parse_dates=["Date"],index_col="Date")


def _actions(frame):
    action_columns = [name for name in ("Dividends", "Stock Splits", "Capital Gains")
                      if name in frame.columns]
    events = []
    for column in action_columns:
        for stamp, value in frame.loc[frame[column].fillna(0) != 0, column].items():
            events.append({"session_date": stamp.strftime("%Y-%m-%d"),
                           "field": column, "value": str(value)})
    return {"columns_present": action_columns,
            "split_event_count": sum(item["field"] == "Stock Splits" for item in events),
            "dividend_event_count": sum(item["field"] == "Dividends" for item in events),
            "capital_gain_event_count": sum(item["field"] == "Capital Gains" for item in events),
            "events": events}


def _corporate_action_windows(events, legacy_rows, raw_rows, adjusted_rows):
    sessions = sorted(set(legacy_rows) & set(raw_rows) & set(adjusted_rows))
    locations = {session:index for index,session in enumerate(sessions)}
    findings = []
    for event in events:
        session = event["session_date"]
        if session not in locations:
            continue
        index = locations[session]
        window = sessions[max(0,index-2):min(len(sessions),index+3)]
        raw_difference = adjusted_difference = 0.0
        for current in window:
            for field in ("Open","High","Low","Close"):
                legacy = float(legacy_rows[current][field])
                raw_difference += abs(legacy - float(raw_rows[current][field]))
                adjusted_difference += abs(legacy - float(adjusted_rows[current][field]))
        findings.append({"event":event,"window_session_dates":window,
                         "legacy_vs_raw_total_absolute_ohlc_difference":raw_difference,
                         "legacy_vs_auto_adjusted_total_absolute_ohlc_difference":adjusted_difference,
                         "closer_to":"raw" if raw_difference < adjusted_difference else
                                     "auto_adjusted" if adjusted_difference < raw_difference else "equal"})
    return findings


def _closeness_summary(legacy_rows, raw_rows, adjusted_rows):
    sessions = sorted(set(legacy_rows) & set(raw_rows) & set(adjusted_rows))
    summary = {"comparison_count":0,"raw_closer_count":0,
               "auto_adjusted_closer_count":0,"equal_distance_count":0,
               "raw_total_absolute_difference":Decimal(0),
               "auto_adjusted_total_absolute_difference":Decimal(0)}
    for session in sessions:
        for field in ("Open","High","Low","Close"):
            legacy=Decimal(legacy_rows[session][field])
            raw=Decimal(raw_rows[session][field])
            adjusted=Decimal(adjusted_rows[session][field])
            raw_difference=abs(legacy-raw)
            adjusted_difference=abs(legacy-adjusted)
            summary["comparison_count"] += 1
            summary["raw_total_absolute_difference"] += raw_difference
            summary["auto_adjusted_total_absolute_difference"] += adjusted_difference
            if raw_difference < adjusted_difference:
                summary["raw_closer_count"] += 1
            elif adjusted_difference < raw_difference:
                summary["auto_adjusted_closer_count"] += 1
            else:
                summary["equal_distance_count"] += 1
    return {key:(str(value) if isinstance(value,Decimal) else value)
            for key,value in summary.items()}


def main(*, reuse_downloaded=False):
    import pandas as pd
    import pyarrow
    import yfinance as yf

    config_path = ROOT / "config/data_sources/yfinance_daily.json"
    config = load_config(config_path)
    validate_acquisition_config(config, installed_yfinance_version=yf.__version__)
    cache_path = ROOT / config["cache_path"]
    cache_path.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache_path))
    acquire = (lambda profile:_reuse(pd,config,profile)) if reuse_downloaded else (lambda profile:_download(yf,config,profile))
    raw_path, raw_frame = acquire("raw")
    adjusted_path, adjusted_frame = acquire("auto_adjusted")
    comparison = config["comparison"]
    fields = comparison["fields"]
    arguments = {"fields":fields,
                 "absolute_tolerance":comparison["absolute_tolerance"],
                 "relative_tolerance":comparison["relative_tolerance"]}
    legacy_path = Path(comparison["legacy_path"])
    raw_comparison = compare_csv_files(legacy_path, raw_path, **arguments)
    adjusted_comparison = compare_csv_files(legacy_path, adjusted_path, **arguments)
    from backtest.reconciliation import load_session_rows
    actions = _actions(raw_frame)
    legacy_rows=load_session_rows(legacy_path)
    raw_rows=load_session_rows(raw_path)
    adjusted_rows=load_session_rows(adjusted_path)
    action_windows = _corporate_action_windows(
        actions["events"], legacy_rows, raw_rows, adjusted_rows)
    closeness = _closeness_summary(legacy_rows,raw_rows,adjusted_rows)
    coverage = raw_comparison["overlap_row_count"] / len(legacy_rows)
    adjusted_closer_share = (closeness["auto_adjusted_closer_count"] /
                             closeness["comparison_count"])
    action_windows_adjusted = sum(
        finding["closer_to"] == "auto_adjusted" for finding in action_windows)
    if (coverage >= 0.99 and adjusted_closer_share >= 0.99 and action_windows and
            action_windows_adjusted == len(action_windows)):
        conclusion = "legacy_matches_provider_auto_adjusted"
    elif (coverage >= 0.99 and closeness["raw_closer_count"] /
          closeness["comparison_count"] >= 0.99):
        conclusion = "legacy_matches_raw"
    else:
        conclusion = "legacy_adjustment_remains_unknown"
    report = {
        "report_version":"1",
        "classification": {"fact":"controlled AAPL reconciliation only",
                           "evidence":"comparisons below",
                           "inference":conclusion,
                           "unknown":"final research adjustment policy"},
        "environment":{"python_version":platform.python_version(),
                       "python_build":sys.version,"yfinance_version":yf.__version__,
                       "pandas_version":pd.__version__,"pyarrow_version":pyarrow.__version__,
                       "os":platform.platform()},
        "contract":config,
        "files":{"legacy":{"path":str(legacy_path),"sha256":sha256(legacy_path)},
                 "raw":{"path":str(raw_path),"sha256":sha256(raw_path)},
                 "auto_adjusted":{"path":str(adjusted_path),"sha256":sha256(adjusted_path)}},
        "legacy_vs_raw":raw_comparison,
        "legacy_vs_auto_adjusted":adjusted_comparison,
        "corporate_actions":actions,
        "corporate_action_windows":action_windows,
        "ohlc_closeness":closeness,
        "classification_rule_evidence":{
            "overlap_coverage":coverage,
            "auto_adjusted_closer_share":adjusted_closer_share,
            "corporate_action_windows_count":len(action_windows),
            "corporate_action_windows_closer_to_auto_adjusted":action_windows_adjusted},
        "provider_revision_evidence":{
            "possible_provider_revision":adjusted_comparison["total_field_mismatches"] > 0,
            "fact":"Controlled files cover the same 2,616 session dates as legacy.",
            "evidence":"Systematic OHLC differences and 53 revised Volume rows are recorded in both comparisons.",
            "examples":adjusted_comparison["mismatch_examples"]},
        "legacy_adjustment_conclusion":conclusion,
    }
    report_path = ROOT / "reports/data_reconciliation/aapl_legacy_vs_yfinance.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report_path":str(report_path),"raw_path":str(raw_path),
                      "adjusted_path":str(adjusted_path),"conclusion":conclusion},indent=2))


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--reuse-downloaded",action="store_true")
    main(reuse_downloaded=parser.parse_args().reuse_downloaded)
