"""Orchestrate fixed-parameter experiments and aggregate factual cross-symbol output."""
import hashlib
import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.experiments import experiment_fingerprint, load_experiment
from backtest.strategy import fingerprint, load_strategy
from scripts.run_research_experiment import run_experiment

COHORT = ("AAPL", "MSFT", "GOOGL", "AMZN", "NVDA")
STRATEGIES = ("breakout_trend_001", "pullback_trend_001", "mean_reversion_001")
EXPECTED_FINGERPRINTS = {
    "breakout_trend_001": "546931f68ca652e24e73da177b08084452ce3183f51d9b17446f39940c52c577",
    "pullback_trend_001": "fa3d18708ee6605cbe644ee580b06d0edb872f454bcb06e04cfd922632db4ac3",
    "mean_reversion_001": "fd60a50a0d1ac3b4181b48e3e07ec03325ded150f2294c4b5c037596fc0e2ab0",
}
IS_WINDOW = {"start": "2015-05-26", "end": "2022-12-30"}
OOS_WINDOW = {"start": "2023-01-03", "end": "2025-10-16"}
RESEARCH_WINDOW = {"start": "2015-05-26", "end": "2025-10-16"}
CORE_METRICS = ("trades", "total_return", "profit_factor", "max_drawdown",
                "sharpe", "expectancy")


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT}", "rev-parse", "HEAD"],
            cwd=ROOT, text=True).strip()
    except Exception:
        return "uncommitted"


def validate_dataset_manifest(manifest, *, symbol):
    required = {"dataset_id", "dataset_version", "symbol", "asset_class", "country",
                "timeframe", "start", "end", "processed_file_sha256",
                "adjustment_method", "quality_summary", "provenance"}
    missing = required - set(manifest)
    if missing:
        raise ValueError(f"{symbol} dataset manifest missing: {sorted(missing)}")
    expected = {"symbol": symbol, "asset_class": "equity", "country": "US",
                "timeframe": "1d", "start": RESEARCH_WINDOW["start"],
                "end": RESEARCH_WINDOW["end"],
                "adjustment_method": "yfinance_auto_adjust"}
    mismatches = [key for key, value in expected.items() if manifest.get(key) != value]
    quality = manifest["quality_summary"]
    quality_failures = [key for key in ("canonical_null_count", "malformed_rows",
                       "duplicate_timestamps", "invalid_ohlc", "negative_volume",
                       "nan_or_infinity") if quality.get(key) != 0]
    if not quality.get("strictly_increasing"):
        quality_failures.append("strictly_increasing")
    if mismatches or quality_failures:
        raise ValueError(f"{symbol} dataset invalid: metadata={mismatches}, quality={quality_failures}")
    return manifest


def _manifest_for_experiment(experiment):
    path = Path(experiment["dataset"]["manifest_path"])
    path = path if path.is_absolute() else ROOT / path
    if not path.is_file():
        raise FileNotFoundError(f"missing symbol dataset manifest: {path}")
    return json.loads(path.read_text())


def _selected_metrics(metrics, *, oos):
    keys = ("trades", "total_return", "profit_factor", "max_drawdown", "sharpe")
    if oos:
        keys += ("expectancy",)
    return {key: metrics[key] for key in keys}


def aggregate_records(records):
    """Deterministic factual aggregation; zero-trade records remain present."""
    ordered = sorted(records, key=lambda item: (COHORT.index(item["symbol"]),
                                                STRATEGIES.index(item["strategy_id"])))
    aggregates = {}
    for strategy_id in STRATEGIES:
        subset = [item for item in ordered if item["strategy_id"] == strategy_id]
        returns = [item["oos"]["total_return"] for item in subset]
        profit_factors = [item["oos"]["profit_factor"] for item in subset
                          if item["oos"]["profit_factor"] is not None]
        sharpes = [item["oos"]["sharpe"] for item in subset]
        aggregates[strategy_id] = {
            "positive_return_symbols": sum(value > 0 for value in returns),
            "negative_return_symbols": sum(value < 0 for value in returns),
            "zero_return_symbols": sum(value == 0 for value in returns),
            "median_oos_return": statistics.median(returns),
            "min_oos_return": min(returns), "max_oos_return": max(returns),
            "median_oos_profit_factor": statistics.median(profit_factors) if profit_factors else None,
            "median_oos_sharpe": statistics.median(sharpes),
            "worst_oos_max_drawdown": max(item["oos"]["max_drawdown"] for item in subset),
            "total_oos_trades": sum(item["oos"]["trades"] for item in subset),
        }
    return {"records": ordered, "aggregates": aggregates}


def _baseline_reference():
    root = ROOT / "reports/experiments/aapl_real_baseline_v1"
    committed = sorted(root.glob("8e17e67335be-*/baseline_summary.json"))
    candidates = committed or sorted(root.glob("*/baseline_summary.json"),
                                     key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError("AAPL baseline reference is missing")
    # The first immutable Phase 3C-2 output is the reference, not a later pilot run.
    return candidates[0], json.loads(candidates[0].read_text())


def _verify_aapl(reference, current):
    expected = {item["strategy_id"]: item for item in reference["strategies"]}
    actual = {item["strategy_id"]: item for item in current["strategies"]}
    for strategy_id in STRATEGIES:
        for segment in ("is_metrics", "oos_metrics"):
            for key in CORE_METRICS:
                if expected[strategy_id][segment][key] != actual[strategy_id][segment][key]:
                    raise RuntimeError(f"AAPL reproduction failed: {strategy_id} {segment} {key}")
    return True


def run_cross_symbol(cohort_path=ROOT / "research/experiments/cross_symbol_pilot_v1.json",
                     output_root=ROOT / "reports/cross_symbol/pilot_v1",
                     experiment_runner=None):
    experiment_runner = experiment_runner or run_experiment
    cohort_path = Path(cohort_path)
    cohort = json.loads(cohort_path.read_text())
    if tuple(cohort.get("symbols", ())) != COHORT or set(cohort.get("experiments", {})) != set(COHORT):
        raise ValueError("pilot cohort must remain exactly AAPL, MSFT, GOOGL, AMZN, NVDA")
    frozen = {family: load_strategy(ROOT / "strategies" / family / "v0.2.0/strategy.yaml")
              for family in STRATEGIES}
    if {family: fingerprint(strategy) for family, strategy in frozen.items()} != EXPECTED_FINGERPRINTS:
        raise RuntimeError("strategy fingerprint drift detected")

    experiments, datasets = {}, {}
    for symbol in COHORT:
        path = ROOT / cohort["experiments"][symbol]
        experiment = load_experiment(path)
        if (experiment["research_window"] != RESEARCH_WINDOW or
                experiment["evaluation"]["in_sample"] != IS_WINDOW or
                experiment["evaluation"]["out_of_sample"] != OOS_WINDOW):
            raise ValueError(f"{symbol} experiment dates differ from fixed cohort dates")
        if [item["strategy_version"] for item in experiment["strategies"]] != ["0.2.0"] * 3:
            raise ValueError(f"{symbol} experiment does not use frozen strategy versions")
        manifest = validate_dataset_manifest(_manifest_for_experiment(experiment), symbol=symbol)
        experiments[symbol] = {"path": path, "spec": experiment,
                               "fingerprint": experiment_fingerprint(experiment)}
        datasets[symbol] = manifest

    commit = _git_commit()
    cohort_checksum = hashlib.sha256(cohort_path.read_bytes()).hexdigest()
    target = Path(output_root) / f"{commit[:12]}-{cohort_checksum[:12]}"
    target.mkdir(parents=True, exist_ok=True)
    records, output_paths = [], {}
    reference_path, reference = _baseline_reference()
    for symbol in COHORT:
        experiment_target = experiment_runner(
            experiments[symbol]["path"], target / symbol)
        output_paths[symbol] = str(experiment_target)
        summary = json.loads((experiment_target / "baseline_summary.json").read_text())
        if symbol == "AAPL":
            _verify_aapl(reference, summary)
        for item in summary["strategies"]:
            if item["fingerprint"] != EXPECTED_FINGERPRINTS[item["strategy_id"]]:
                raise RuntimeError("strategy fingerprint changed during experiment")
            if item["costs"] != {"commission_per_trade": 1.0, "slippage_bps": 5}:
                raise RuntimeError("cross-symbol costs differ from canonical baseline")
            records.append({
                "symbol": symbol, "strategy_id": item["strategy_id"],
                "strategy_version": item["version"], "strategy_fingerprint": item["fingerprint"],
                "dataset_id": datasets[symbol]["dataset_id"],
                "dataset_version": datasets[symbol]["dataset_version"],
                "dataset_checksum": datasets[symbol]["processed_file_sha256"],
                "experiment_fingerprint": experiments[symbol]["fingerprint"],
                "is": _selected_metrics(item["is_metrics"], oos=False),
                "oos": _selected_metrics(item["oos_metrics"], oos=True),
            })
    if {family: fingerprint(load_strategy(ROOT / "strategies" / family / "v0.2.0/strategy.yaml"))
            for family in STRATEGIES} != EXPECTED_FINGERPRINTS:
        raise RuntimeError("strategy parameters mutated during cross-symbol run")
    aggregated = aggregate_records(records)
    summary = {
        "cohort_id": cohort["cohort_id"], "symbols": list(COHORT),
        "is_window": IS_WINDOW, "oos_window": OOS_WINDOW,
        "canonical_costs": {"commission_per_trade": 1.0, "slippage_bps": 5},
        **aggregated,
        "limitations": cohort["limitations"],
    }
    manifest = {
        "cohort_id": cohort["cohort_id"], "cohort_checksum": cohort_checksum,
        "git_commit": commit, "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "aapl_reproduction": {"status": "passed", "reference": str(reference_path)},
        "datasets": {symbol: {"dataset_id": data["dataset_id"],
                              "version": data["dataset_version"],
                              "checksum": data["processed_file_sha256"]}
                     for symbol, data in datasets.items()},
        "experiments": {symbol: {"path": str(item["path"]),
                                 "fingerprint": item["fingerprint"]}
                        for symbol, item in experiments.items()},
        "strategies": EXPECTED_FINGERPRINTS,
        "experiment_outputs": output_paths,
        "boundary_mode": "flat_start",
        "warmup_policy": "pre_segment_history_for_indicators_only_no_signals_fills_or_pnl",
        "limitations": cohort["limitations"],
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (target / "cross_symbol_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(target)
    return target


if __name__ == "__main__":
    run_cross_symbol()
