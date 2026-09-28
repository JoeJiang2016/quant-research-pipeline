"""Precommitted, performance-blind holdout acquisition and fixed IS/OOS evaluation."""
import csv
import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.reconciliation import load_config
from backtest.strategy import fingerprint, load_strategy
from scripts.download_yfinance_dataset import acquire
from scripts.run_cross_symbol_rolling import percentile
from scripts.run_cross_symbol_validation import EXPECTED_FINGERPRINTS, STRATEGIES
from scripts.run_research_experiment import run_experiment

COHORT_ID = "us_equity_holdout_v1"
SEED = "quant_research_holdout_v1"
SEEN_PILOT = ("AAPL", "MSFT", "GOOGL", "AMZN", "NVDA")
SOURCE_PATH = Path(r"C:\Projects\backtest_app\data\0.0 list.csv")
SOURCE_SHA256 = "6ea4b1031d75314c0c6f90f616e300f70b5d04856af8a0cb98908dbd3922f027"
COHORT_PATH = ROOT / "research/cohorts/us_equity_holdout_v1.json"
RESEARCH_WINDOW = {"start": "2015-05-26", "end": "2025-10-16"}
IS_WINDOW = {"start": "2015-05-26", "end": "2022-12-30"}
OOS_WINDOW = {"start": "2023-01-03", "end": "2025-10-16"}
CANONICAL_COSTS = {"commission_per_trade": 1.0, "slippage_bps": 5}


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_symbols(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        values = [row["Symbol"].strip().upper() for row in csv.DictReader(handle)]
    values = [value for value in values if value]
    return values, sorted(set(values))


def deterministic_selection(symbols, count=30):
    candidates = set(symbols) - set(SEEN_PILOT)
    keyed = [(hashlib.sha256(f"{SEED}:{symbol}".encode()).hexdigest(), symbol)
             for symbol in candidates]
    return [symbol for _, symbol in sorted(keyed)[:count]]


def validate_frozen_cohort(path=COHORT_PATH, source_path=SOURCE_PATH,
                           expected_sha256=SOURCE_SHA256):
    cohort = json.loads(Path(path).read_text())
    raw, unique = normalized_symbols(source_path)
    failures = []
    if cohort["cohort_id"] != COHORT_ID:
        failures.append("cohort_id")
    if (file_sha256(source_path) != expected_sha256 or
            cohort["source_file_sha256"] != expected_sha256):
        failures.append("source_file_sha256")
    if cohort["source_symbol_count"] != len(raw):
        failures.append("source_symbol_count")
    if cohort["duplicate_count"] != len(raw) - len(unique):
        failures.append("duplicate_count")
    if cohort["selected_symbols"] != deterministic_selection(unique):
        failures.append("selected_symbols")
    if set(cohort["selected_symbols"]) & set(SEEN_PILOT):
        failures.append("seen_pilot_exclusion")
    if failures:
        raise RuntimeError(f"frozen cohort validation failed: {failures}")
    return cohort


def acquisition_config(symbol):
    """Build the explicit contract consumed by the canonical single-symbol layer."""
    slug = symbol.lower().replace(".", "-")
    return {
        "contract_version": "2", "acquisition_id": f"{slug}_1d_yf_holdout_v1",
        "provider": "Yahoo Finance", "library": "yfinance", "library_version": "1.7.0",
        "function": "yfinance.download", "cache_path": ".deps/yfinance-cache",
        "symbol": symbol, "start": RESEARCH_WINDOW["start"], "end_exclusive": "2025-10-17",
        "timestamp_semantics": "session_date",
        "download_semantics": {"start_inclusive": True, "end_exclusive": True, "period": None},
        "common_parameters": {"interval": "1d", "back_adjust": False, "actions": True,
            "prepost": False, "repair": False, "progress": False, "threads": False,
            "multi_level_index": False, "ignore_tz": True, "group_by": "column",
            "keepna": False, "rounding": False, "timeout": 30},
        "profiles": {
            "raw": {"auto_adjust": False, "dataset_id": f"{slug}_1d_yf_raw",
                    "dataset_version": "1",
                    "artifact_path": f"data/provider/yfinance/{slug}_1d_yf_holdout_v1/provider_raw.csv",
                    "price_adjustment": "raw",
                    "adjustment_method": "yfinance_auto_adjust_false_provider_view"},
            "auto_adjusted": {"auto_adjust": True,
                    "dataset_id": f"{slug}_1d_yf_adjusted", "dataset_version": "1",
                    "artifact_path": f"data/provider/yfinance/{slug}_1d_yf_holdout_v1/provider_auto_adjusted.csv",
                    "price_adjustment": "provider_adjusted",
                    "adjustment_method": "yfinance_auto_adjust"}},
        "acquisition_manifest_path": f"data/acquisitions/{slug}_1d_yf_holdout_v1.json",
        "canonical_column_mapping": {"timestamp": "Date", "open": "Open", "high": "High",
                                     "low": "Low", "close": "Close", "volume": "Volume"},
        "session_policy": "Yahoo Finance daily session labels; no calendar repair",
        "asset_class": "equity", "country": "US"}


def _status_from_result(symbol, result):
    adjusted = result["auto_adjusted"]["manifest"]
    quality = adjusted["quality_summary"]
    bad_quality = [key for key in ("canonical_null_count", "malformed_rows",
                   "duplicate_timestamps", "invalid_ohlc", "negative_volume",
                   "nan_or_infinity") if quality.get(key) != 0]
    if not quality.get("strictly_increasing"):
        bad_quality.append("strictly_increasing")
    status, reason = "valid", None
    if adjusted["start"] != RESEARCH_WINDOW["start"] or adjusted["end"] != RESEARCH_WINDOW["end"]:
        status, reason = "insufficient_history", (
            f"required {RESEARCH_WINDOW['start']} through {RESEARCH_WINDOW['end']}; "
            f"received {adjusted['start']} through {adjusted['end']}")
    elif bad_quality:
        status, reason = "invalid", f"canonical quality failures: {bad_quality}"
    acquisition = result["acquisition_manifest"]
    return {"symbol": symbol, "status": status, "reason": reason,
            "attempts": 1, "dataset_id": adjusted["dataset_id"],
            "dataset_version": adjusted["dataset_version"],
            "dataset_manifest_path": str(result["auto_adjusted"]["manifest_path"]),
            "dataset_checksum": adjusted["processed_file_sha256"],
            "raw_checksum": acquisition["provider_artifacts"]["raw"]["sha256"],
            "adjusted_provider_checksum": acquisition["provider_artifacts"]["auto_adjusted"]["sha256"],
            "corporate_action_counts": acquisition["corporate_actions"]["event_counts"]}


def acquire_cohort(cohort, *, yf, max_attempts=2, acquire_one=acquire,
                   status_path=None):
    """Acquire in frozen order; bounded failures remain in the output and cohort."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    status_path = Path(status_path or ROOT / "reports/cross_symbol/holdout_v1/acquisition_status.json")
    prior = {}
    if status_path.exists():
        prior = {item["symbol"]: item for item in json.loads(status_path.read_text())["symbols"]}
    statuses = []
    for symbol in cohort["selected_symbols"]:
        if prior.get(symbol, {}).get("status") in {"valid", "invalid", "insufficient_history"}:
            statuses.append(prior[symbol]); continue
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                current = _status_from_result(symbol, acquire_one(acquisition_config(symbol), yf=yf))
                current["attempts"] = attempt; statuses.append(current); break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
        else:
            statuses.append({"symbol": symbol, "status": "acquisition_failed",
                             "reason": last_error, "attempts": max_attempts})
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(json.dumps({"cohort_id": COHORT_ID, "max_attempts": max_attempts,
                                           "symbols": statuses}, indent=2) + "\n")
    payload = {"cohort_id": COHORT_ID, "max_attempts": max_attempts, "symbols": statuses}
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def freeze_experiment_specs(statuses, spec_root=ROOT / "research/experiments/holdout_v1"):
    spec_root = Path(spec_root); spec_root.mkdir(parents=True, exist_ok=True)
    paths = {}
    for item in statuses:
        if item["status"] != "valid":
            continue
        symbol = item["symbol"]
        manifest_path = Path(item["dataset_manifest_path"])
        try:
            manifest_path = manifest_path.resolve().relative_to(ROOT.resolve())
        except ValueError:
            pass
        spec = {
            "experiment_id": f"{symbol.lower()}_holdout_v1", "experiment_version": "1.0.0",
            "description": f"Precommitted fixed-date holdout baseline for {symbol}.",
            "dataset": {"dataset_id": item["dataset_id"],
                        "manifest_path": str(manifest_path).replace("\\", "/")},
            "strategies": [{"strategy_id": strategy_id, "strategy_version": "0.2.0"}
                           for strategy_id in STRATEGIES],
            "research_window": RESEARCH_WINDOW,
            "evaluation": {"in_sample": IS_WINDOW, "out_of_sample": OOS_WINDOW},
            "walk_forward": {"enabled": False, "train_bars": 1, "test_bars": 1, "step_bars": 1},
            "cost_sensitivity": {"enabled": False, "scenarios": [{
                "name": "canonical_strategy_costs", "commission_multiplier": 1.0,
                "slippage_multiplier": 1.0}]}}
        path = spec_root / f"{symbol.lower()}.yaml"
        content = yaml.safe_dump(spec, sort_keys=False)
        if path.exists() and path.read_text() != content:
            raise FileExistsError(f"immutable experiment spec differs: {path}")
        path.write_text(content); paths[symbol] = path
    return paths


def aggregate_holdout(records, invalid_count):
    output = {}
    for strategy_id in STRATEGIES:
        subset = [item for item in records if item["strategy_id"] == strategy_id]
        returns = [item["oos"]["total_return"] for item in subset]
        pfs = [item["oos"]["profit_factor"] for item in subset
               if item["oos"]["profit_factor"] is not None]
        output[strategy_id] = {
            "valid_symbol_count": len(subset), "invalid_symbol_count": invalid_count,
            "positive_oos_symbols": sum(value > 0 for value in returns),
            "negative_oos_symbols": sum(value < 0 for value in returns),
            "zero_return_oos_symbols": sum(value == 0 for value in returns),
            "median_oos_return": statistics.median(returns),
            "oos_return_25th_percentile": percentile(returns, .25),
            "oos_return_75th_percentile": percentile(returns, .75),
            "min_oos_return": min(returns), "max_oos_return": max(returns),
            "median_oos_profit_factor": statistics.median(pfs) if pfs else None,
            "median_oos_sharpe": statistics.median(item["oos"]["sharpe"] for item in subset),
            "worst_oos_max_drawdown": max(item["oos"]["max_drawdown"] for item in subset),
            "total_oos_trades": sum(item["oos"]["trades"] for item in subset)}
    return output


def _git_commit():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def run_holdout(status_path, output_root=ROOT / "reports/cross_symbol/holdout_v1",
                experiment_runner=run_experiment):
    cohort = validate_frozen_cohort()
    statuses = json.loads(Path(status_path).read_text())["symbols"]
    if [item["symbol"] for item in statuses] != cohort["selected_symbols"]:
        raise RuntimeError("acquisition statuses do not preserve frozen cohort order")
    valid = [item for item in statuses if item["status"] == "valid"]
    specs = freeze_experiment_specs(statuses)
    strategies = {name: load_strategy(ROOT / f"strategies/{name}/v0.2.0/strategy.yaml")
                  for name in STRATEGIES}
    if {name: fingerprint(value) for name, value in strategies.items()} != EXPECTED_FINGERPRINTS:
        raise RuntimeError("strategy fingerprint drift detected")
    if any({"commission_per_trade": value["execution"]["commission_per_trade"],
            "slippage_bps": value["execution"]["slippage_bps"]} != CANONICAL_COSTS
           for value in strategies.values()):
        raise RuntimeError("canonical costs drift detected")
    commit = _git_commit()
    cohort_checksum = file_sha256(COHORT_PATH)
    target = Path(output_root) / f"{commit[:12]}-{cohort_checksum[:12]}"
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for item in valid:
        symbol = item["symbol"]
        result_path = experiment_runner(specs[symbol], target / symbol)
        summary = json.loads((result_path / "baseline_summary.json").read_text())
        experiment_manifest = json.loads((result_path / "experiment_manifest.json").read_text())
        for strategy in summary["strategies"]:
            if strategy["fingerprint"] != EXPECTED_FINGERPRINTS[strategy["strategy_id"]]:
                raise RuntimeError("strategy fingerprint changed during holdout execution")
            if strategy["costs"] != CANONICAL_COSTS:
                raise RuntimeError("holdout costs differ from canonical baseline")
            keys = ("trades", "total_return", "profit_factor", "max_drawdown", "sharpe", "expectancy")
            records.append({"symbol": symbol, "strategy_id": strategy["strategy_id"],
                "strategy_version": strategy["version"], "strategy_fingerprint": strategy["fingerprint"],
                "dataset_id": item["dataset_id"], "dataset_checksum": item["dataset_checksum"],
                "experiment_fingerprint": experiment_manifest["experiment_fingerprint"],
                "is": {key: strategy["is_metrics"][key] for key in keys},
                "oos": {key: strategy["oos_metrics"][key] for key in keys}})
    invalid_count = len(statuses) - len(valid)
    summary = {"cohort_id": COHORT_ID, "cohort_role": "unseen_holdout_cohort",
        "seen_pilot_cohort": list(SEEN_PILOT), "symbols": cohort["selected_symbols"],
        "status_counts": {name: sum(item["status"] == name for item in statuses)
                          for name in ("valid", "invalid", "acquisition_failed", "insufficient_history")},
        "records": records, "aggregates": aggregate_holdout(records, invalid_count),
        "limitations": [
            "The source list is a modern symbol snapshot, not point-in-time constituent history; survivorship and constituent-history bias remain.",
            "The upstream origin of the source symbol list is UNKNOWN.",
            "Holdout results are kept separate from the seen pilot cohort and are not a continuous portfolio."]}
    manifest = {"cohort_id": COHORT_ID, "cohort_checksum": cohort_checksum,
        "cohort_role": "unseen_holdout_cohort", "seen_pilot_cohort": list(SEEN_PILOT),
        "git_commit": commit, "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "research_window": RESEARCH_WINDOW, "is_window": IS_WINDOW, "oos_window": OOS_WINDOW,
        "canonical_costs": CANONICAL_COSTS, "boundary_mode": "flat_start",
        "parameter_selection": "none", "rolling_oos": False,
        "strategies": EXPECTED_FINGERPRINTS,
        "acquisition_status_source": str(Path(status_path)),
        "experiment_specs": {symbol: str(path) for symbol, path in specs.items()}}
    (target / "acquisition_status.json").write_text(json.dumps({"cohort_id": COHORT_ID,
        "symbols": statuses}, indent=2) + "\n")
    (target / "holdout_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(target)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("acquire", "run"))
    parser.add_argument("--status", type=Path,
                        default=ROOT / "reports/cross_symbol/holdout_v1/acquisition_status.json")
    arguments = parser.parse_args()
    frozen = validate_frozen_cohort()
    if arguments.mode == "acquire":
        import yfinance as yf
        result = acquire_cohort(frozen, yf=yf, status_path=arguments.status)
        print(arguments.status)
        print(json.dumps({name: sum(item["status"] == name for item in result["symbols"])
                          for name in ("valid", "invalid", "acquisition_failed",
                                       "insufficient_history")}, sort_keys=True))
    else:
        run_holdout(arguments.status)
