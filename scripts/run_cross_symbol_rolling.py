"""Fixed-parameter rolling OOS robustness across the frozen five-symbol cohort."""
import hashlib
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.datasets import load_dataset
from backtest.engine.core import metrics, run
from backtest.strategy import fingerprint, load_strategy
from backtest.walk_forward import build_folds, stitched_oos_equity
from scripts.run_aapl_robustness import FOLD_CONFIG
from scripts.run_cross_symbol_validation import (
    COHORT, EXPECTED_FINGERPRINTS, STRATEGIES, _git_commit,
    validate_dataset_manifest,
)

MANIFEST_PATHS = {
    "AAPL": "data/manifests/aapl_1d_yf_adjusted_v2.json",
    "MSFT": "data/manifests/msft_1d_yf_adjusted_v1.json",
    "GOOGL": "data/manifests/googl_1d_yf_adjusted_v1.json",
    "AMZN": "data/manifests/amzn_1d_yf_adjusted_v1.json",
    "NVDA": "data/manifests/nvda_1d_yf_adjusted_v1.json",
}
EXPECTED_DATASET_CHECKSUMS = {
    "AAPL": "aa3ba9ad71c7c509f8b26cd6c4c4a28d6a2b6777dc74a0ec9e33f499910f334c",
    "MSFT": "5eae99ee65da82f20fe2a02b05ba2ac6b74733d9adecf432a6a61450fce67857",
    "GOOGL": "35f4a08c4db7647802ae262aa85e7abd73b90dff8f218a0d04820312ff16b2f1",
    "AMZN": "086f44fb122e687614d5982ff9e1de9509f66335020d31e259665d7e5ff66811",
    "NVDA": "8ac589f81026606ab8e2f63ef9b58bbb97a7f3a511a4c5b1c66744f7f8fe4942",
}
CANONICAL_COSTS = {"commission_per_trade": 1.0, "slippage_bps": 5}
FOLD_METRICS = ("trades", "total_return", "profit_factor", "max_drawdown",
                "sharpe", "expectancy", "commission", "slippage")


def percentile(values, probability):
    """Inclusive linear percentile with deterministic behavior for small samples."""
    if not values or not 0 <= probability <= 1:
        raise ValueError("percentile requires values and probability in [0, 1]")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def stitch_symbol_curves(symbol_curves):
    """Stitch independent fold curves for exactly one symbol."""
    symbols = {item["symbol"] for item in symbol_curves}
    if len(symbols) != 1:
        raise ValueError("stitched OOS equity cannot combine symbols")
    return {"symbol": next(iter(symbols)), "points": stitched_oos_equity(
        [item["curve"] for item in symbol_curves])}


def summarize_folds(records):
    returns = [item["metrics"]["total_return"] for item in records]
    pfs = [item["metrics"]["profit_factor"] for item in records
           if item["metrics"]["profit_factor"] is not None]
    return {
        "fold_count": len(records),
        "positive_return_folds": sum(value > 0 for value in returns),
        "negative_return_folds": sum(value < 0 for value in returns),
        "zero_return_folds": sum(value == 0 for value in returns),
        "median_fold_return": statistics.median(returns),
        "min_fold_return": min(returns), "max_fold_return": max(returns),
        "median_profit_factor": statistics.median(pfs) if pfs else None,
        "median_sharpe": statistics.median(item["metrics"]["sharpe"] for item in records),
        "worst_max_drawdown": max(item["metrics"]["max_drawdown"] for item in records),
        "total_oos_trades": sum(item["metrics"]["trades"] for item in records),
    }


def aggregate_cells(records):
    output = {}
    for strategy_id in STRATEGIES:
        subset = [item for item in records if item["strategy_id"] == strategy_id]
        returns = [item["metrics"]["total_return"] for item in subset]
        pfs = [item["metrics"]["profit_factor"] for item in subset
               if item["metrics"]["profit_factor"] is not None]
        output[strategy_id] = {
            "cell_count": len(subset),
            "positive_return_cells": sum(value > 0 for value in returns),
            "negative_return_cells": sum(value < 0 for value in returns),
            "zero_return_cells": sum(value == 0 for value in returns),
            "positive_return_percentage": 100 * sum(value > 0 for value in returns) / len(returns),
            "median_return": statistics.median(returns),
            "return_25th_percentile": percentile(returns, 0.25),
            "return_75th_percentile": percentile(returns, 0.75),
            "min_return": min(returns), "max_return": max(returns),
            "median_profit_factor": statistics.median(pfs) if pfs else None,
            "median_sharpe": statistics.median(item["metrics"]["sharpe"] for item in subset),
            "worst_max_drawdown": max(item["metrics"]["max_drawdown"] for item in subset),
            "total_oos_trades": sum(item["metrics"]["trades"] for item in subset),
        }
    return output


def fold_breadth(records):
    output = {}
    for strategy_id in STRATEGIES:
        rows = []
        for fold_id in sorted({item["fold_id"] for item in records}):
            subset = [item for item in records
                      if item["strategy_id"] == strategy_id and item["fold_id"] == fold_id]
            if len(subset) != len(COHORT) or len({(item["test_start"], item["test_end"])
                                                  for item in subset}) != 1:
                raise ValueError(f"incomplete or misaligned breadth cell: {strategy_id} {fold_id}")
            values = [item["metrics"]["total_return"] for item in subset]
            rows.append({"fold_id": fold_id, "test_start": subset[0]["test_start"],
                         "test_end": subset[0]["test_end"],
                         "positive_symbols": sum(value > 0 for value in values),
                         "negative_symbols": sum(value < 0 for value in values),
                         "zero_symbols": sum(value == 0 for value in values),
                         "median_return": statistics.median(values)})
        output[strategy_id] = rows
    return output


def _aapl_reference():
    paths = sorted((ROOT / "reports/robustness/aapl_v0_2_0").glob(
        "9c9a1a1bd034-*/breakout_trend_001/folds.json"))
    if not paths:
        raise FileNotFoundError("Phase 3C-3 AAPL rolling reference is required")
    return paths[0].parents[1]


def verify_aapl_folds(current_by_strategy, reference_root):
    for strategy_id in STRATEGIES:
        expected = json.loads((Path(reference_root) / strategy_id / "folds.json").read_text())
        current = current_by_strategy[strategy_id]
        if len(current) != len(expected):
            raise RuntimeError(f"AAPL fold count differs: {strategy_id}")
        for actual, prior in zip(current, expected):
            for key in ("fold_id", "train_start", "train_end", "test_start", "test_end"):
                if actual[key] != prior[key]:
                    raise RuntimeError(f"AAPL fold boundary differs: {strategy_id} {actual['fold_id']} {key}")
            for key in FOLD_METRICS:
                if actual["metrics"][key] != prior["metrics"][key]:
                    raise RuntimeError(f"AAPL fold metric differs: {strategy_id} {actual['fold_id']} {key}")
    return True


def _load_inputs():
    datasets = {}
    for symbol in COHORT:
        manifest = validate_dataset_manifest(
            json.loads((ROOT / MANIFEST_PATHS[symbol]).read_text()), symbol=symbol)
        if manifest["processed_file_sha256"] != EXPECTED_DATASET_CHECKSUMS[symbol]:
            raise RuntimeError(f"{symbol} dataset checksum drift detected")
        bars = load_dataset(manifest["processed_path"], symbol=symbol,
                            timeframe=manifest["timeframe"],
                            timestamp_semantics=manifest["timestamp_semantics"])
        datasets[symbol] = (manifest, bars)
    strategies = {item: load_strategy(ROOT / "strategies" / item / "v0.2.0/strategy.yaml")
                  for item in STRATEGIES}
    if {key: fingerprint(value) for key, value in strategies.items()} != EXPECTED_FINGERPRINTS:
        raise RuntimeError("strategy fingerprint drift detected")
    if any({"commission_per_trade": item["execution"]["commission_per_trade"],
            "slippage_bps": item["execution"]["slippage_bps"]} != CANONICAL_COSTS
           for item in strategies.values()):
        raise RuntimeError("strategy execution costs differ from canonical baseline")
    return datasets, strategies


def run_cross_symbol_rolling(output_root=ROOT / "reports/cross_symbol/pilot_rolling_v1"):
    datasets, strategies = _load_inputs()
    row_counts = {len(bars) for _, bars in datasets.values()}
    if row_counts != {2616}:
        raise RuntimeError(f"cohort row counts differ from frozen input: {row_counts}")
    folds = build_folds(2616, train_bars=756, test_bars=252, step=252, anchored=False)
    if len(folds) != 7:
        raise RuntimeError("expected exactly seven complete folds")
    cohort_digest = hashlib.sha256("".join(EXPECTED_DATASET_CHECKSUMS[s]
                                             for s in COHORT).encode()).hexdigest()
    commit = _git_commit()
    target = Path(output_root) / f"{commit[:12]}-{cohort_digest[:12]}"
    target.mkdir(parents=True, exist_ok=True)
    all_records, symbol_summaries, aapl_records = [], {}, {}
    for symbol in COHORT:
        manifest, bars = datasets[symbol]
        symbol_summaries[symbol] = {}
        for strategy_id in STRATEGIES:
            strategy = strategies[strategy_id]
            records, curves = [], []
            for fold in folds:
                fold_bars = bars[fold.train_start:fold.test_end]
                evaluation_start = fold.train_end - fold.train_start
                result = run(strategy, fold_bars, evaluation_start=evaluation_start,
                             evaluation_end=len(fold_bars) - 1)
                fold_metrics = metrics(result, strategy["risk"]["initial_equity"])
                record = {
                    "symbol": symbol, "strategy_id": strategy_id,
                    "strategy_version": strategy["strategy_version"],
                    "strategy_fingerprint": fingerprint(strategy),
                    "dataset_id": manifest["dataset_id"],
                    "dataset_version": manifest["dataset_version"],
                    "dataset_checksum": manifest["processed_file_sha256"],
                    "fold_id": fold.fold_id,
                    "train_start": fold_bars[0]["timestamp"],
                    "train_end": fold_bars[evaluation_start - 1]["timestamp"],
                    "test_start": fold_bars[evaluation_start]["timestamp"],
                    "test_end": fold_bars[-1]["timestamp"],
                    "trade_count": fold_metrics["trades"],
                    "total_return": fold_metrics["total_return"],
                    "win_rate": fold_metrics["win_rate"],
                    "expectancy": fold_metrics["expectancy"],
                    "profit_factor": fold_metrics["profit_factor"],
                    "max_drawdown": fold_metrics["max_drawdown"],
                    "sharpe": fold_metrics["sharpe"],
                    "sortino": fold_metrics["sortino"],
                    "cagr": fold_metrics["cagr"],
                    "commission": fold_metrics["commission"],
                    "slippage": fold_metrics["slippage"],
                    "metrics": fold_metrics,
                    "ending_position_open": result["ending_position_open"],
                    "ending_unrealized_pnl": result["ending_unrealized_pnl"],
                }
                if any(not (record["test_start"] <= trade["entry_time"] <= record["test_end"])
                           for trade in result["trades"]):
                    raise AssertionError("warmup trade leaked into OOS fold")
                records.append(record); all_records.append(record)
                curves.append({"symbol": symbol, "curve": result["equity_curve"]})
            strategy_dir = target / symbol / strategy_id
            strategy_dir.mkdir(parents=True, exist_ok=True)
            (strategy_dir / "folds.json").write_text(json.dumps(records, indent=2) + "\n")
            stitched = stitch_symbol_curves(curves)
            stitched["interpretation"] = "chronological OOS points from independent flat-start folds for one symbol"
            (strategy_dir / "stitched_oos_equity.json").write_text(json.dumps(stitched, indent=2) + "\n")
            symbol_summaries[symbol][strategy_id] = summarize_folds(records)
            if symbol == "AAPL":
                aapl_records[strategy_id] = records
    if len(all_records) != 105:
        raise RuntimeError(f"expected 105 symbol-strategy-fold cells, got {len(all_records)}")
    reference = _aapl_reference()
    verify_aapl_folds(aapl_records, reference)
    aggregate = aggregate_cells(all_records)
    breadth = fold_breadth(all_records)
    (target / "per_symbol_summary.json").write_text(json.dumps(symbol_summaries, indent=2) + "\n")
    (target / "aggregate_summary.json").write_text(json.dumps(aggregate, indent=2) + "\n")
    (target / "fold_breadth.json").write_text(json.dumps(breadth, indent=2) + "\n")
    manifest = {
        "analysis": "fixed_parameter_cross_symbol_rolling_oos_robustness",
        "parameter_selection": "none", "symbols": list(COHORT),
        "strategies": EXPECTED_FINGERPRINTS,
        "datasets": {symbol: {"dataset_id": item[0]["dataset_id"],
                               "version": item[0]["dataset_version"],
                               "checksum": item[0]["processed_file_sha256"]}
                     for symbol, item in datasets.items()},
        "fold_configuration": FOLD_CONFIG, "complete_fold_count": 7,
        "excluded_tail_bars": 96, "cell_count": 105,
        "canonical_costs": CANONICAL_COSTS,
        "boundary_mode": "flat_start_each_fold",
        "warmup_policy": "training bars are indicator warmup only; no IS signals, fills, positions, or PnL",
        "aapl_phase3c3_reproduction": {"status": "passed", "reference": str(reference)},
        "git_commit": commit, "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "interpretation": "Each cell is an independent symbol/fold backtest; outputs are not a continuous portfolio.",
        "limitations": [
            "The five US mega-cap equities are correlated and do not constitute five independent trials.",
            "This is descriptive robustness evidence only; it is not a significance test or regime analysis.",
            "No parameter search, parameter selection, or cost sweep was performed.",
        ],
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(target)
    return target


if __name__ == "__main__":
    run_cross_symbol_rolling()
