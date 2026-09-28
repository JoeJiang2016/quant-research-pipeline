"""Fixed-parameter AAPL cost and rolling-OOS robustness analysis."""
import json
import statistics
import subprocess
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
from scripts.run_research_experiment import BOUNDARY_MODE, WARMUP_POLICY

STRATEGIES = ("breakout_trend_001", "pullback_trend_001", "mean_reversion_001")
COST_SCENARIOS = (
    {"name": "frictionless_diagnostic", "commission_per_trade": 0.0, "slippage_bps": 0},
    {"name": "baseline", "commission_per_trade": 1.0, "slippage_bps": 5},
    {"name": "higher_friction", "commission_per_trade": 1.0, "slippage_bps": 10},
    {"name": "stress_friction", "commission_per_trade": 2.0, "slippage_bps": 20},
)
FOLD_CONFIG = {"train_bars": 756, "test_bars": 252, "step_bars": 252,
               "anchored": False, "incomplete_final_fold": "excluded"}
BASELINE_OOS = {"start": "2023-01-03", "end": "2025-10-16"}
REPRODUCTION_METRICS = ("trades", "total_return", "win_rate", "expectancy",
                        "profit_factor", "max_drawdown", "sharpe", "sortino",
                        "cagr", "commission", "slippage")


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT}", "rev-parse", "HEAD"],
            cwd=ROOT, text=True).strip()
    except Exception:
        return "uncommitted"


def _load_inputs():
    manifest = json.loads((ROOT / "data/manifests/aapl_1d_yf_adjusted_v2.json").read_text())
    bars = load_dataset(
        manifest["processed_path"], symbol=manifest["symbol"],
        timeframe=manifest["timeframe"],
        timestamp_semantics=manifest["timestamp_semantics"])
    strategies = {
        family: load_strategy(ROOT / "strategies" / family / "v0.2.0/strategy.yaml")
        for family in STRATEGIES}
    return manifest, bars, strategies


def _indices(bars, start, end):
    active = [i for i, bar in enumerate(bars) if start <= bar["timestamp"] <= end]
    if not active:
        raise ValueError("evaluation window contains no bars")
    return active[0], active[-1]


def _runtime(strategy, costs):
    import copy
    candidate = copy.deepcopy(strategy)
    candidate["execution"]["commission_per_trade"] = costs["commission_per_trade"]
    candidate["execution"]["slippage_bps"] = costs["slippage_bps"]
    return candidate


def _result_payload(strategy, result, costs):
    return {
        "applied_costs": costs,
        "strategy_fingerprint": fingerprint(strategy),
        "metrics": metrics(result, strategy["risk"]["initial_equity"]),
        "ending_position_open": result["ending_position_open"],
        "ending_unrealized_pnl": result["ending_unrealized_pnl"],
        "trade_path": [{key: trade[key] for key in ("signal_time", "entry_time", "exit_time")}
                       for trade in result["trades"]],
    }


def _baseline_reference():
    root = ROOT / "reports/experiments/aapl_real_baseline_v1"
    candidates = sorted(root.glob("*/baseline_summary.json"),
                        key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError("Phase 3C-2 baseline summary is required")
    return candidates[0], json.loads(candidates[0].read_text())


def _reproduce_baseline(bars, strategies):
    reference_path, reference = _baseline_reference()
    start, end = _indices(bars, "2015-05-26", "2025-10-16")
    windows = {"is_metrics": ("2015-05-26", "2022-12-30"),
               "oos_metrics": ("2023-01-03", "2025-10-16")}
    reproduced = {}
    reference_by_id = {item["strategy_id"]: item for item in reference["strategies"]}
    for family, strategy in strategies.items():
        reproduced[family] = {}
        for label, (window_start, window_end) in windows.items():
            active_start, active_end = _indices(bars[start:end + 1], window_start, window_end)
            result = run(strategy, bars[start:end + 1], evaluation_start=active_start,
                         evaluation_end=active_end)
            current = metrics(result, strategy["risk"]["initial_equity"])
            expected = reference_by_id[family][label]
            for key in REPRODUCTION_METRICS:
                if current[key] != expected[key]:
                    raise RuntimeError(f"baseline reproduction failed: {family} {label} {key}")
            reproduced[family][label] = {key: current[key] for key in REPRODUCTION_METRICS}
    return {"status": "passed", "reference": str(reference_path),
            "compared_metrics": list(REPRODUCTION_METRICS), "results": reproduced}


def _cost_sensitivity(bars, strategies):
    start, end = _indices(bars, BASELINE_OOS["start"], BASELINE_OOS["end"])
    output = {}
    for family, strategy in strategies.items():
        scenarios = {}
        baseline_path = None
        for scenario in COST_SCENARIOS:
            runtime = _runtime(strategy, scenario)
            result = run(runtime, bars, evaluation_start=start, evaluation_end=end)
            payload = _result_payload(strategy, result, scenario)
            if scenario["name"] == "baseline":
                baseline_path = payload["trade_path"]
            scenarios[scenario["name"]] = payload
        for payload in scenarios.values():
            payload["trade_path_changed_vs_baseline"] = payload["trade_path"] != baseline_path
            payload["path_change_reason"] = (
                "execution costs can change fills, stop/target levels, equity-based sizing, and later position availability"
                if payload["trade_path_changed_vs_baseline"] else None)
            del payload["trade_path"]
        output[family] = scenarios
    return output


def _fold_summary(fold_results):
    returns = [fold["metrics"]["total_return"] for fold in fold_results]
    profit_factors = [fold["metrics"]["profit_factor"] for fold in fold_results
                      if fold["metrics"]["profit_factor"] is not None]
    return {
        "fold_count": len(fold_results),
        "positive_return_folds": sum(value > 0 for value in returns),
        "negative_return_folds": sum(value < 0 for value in returns),
        "zero_return_folds": sum(value == 0 for value in returns),
        "median_fold_return": statistics.median(returns),
        "min_fold_return": min(returns), "max_fold_return": max(returns),
        "median_profit_factor": statistics.median(profit_factors) if profit_factors else None,
        "worst_max_drawdown": max(fold["metrics"]["max_drawdown"] for fold in fold_results),
        "total_oos_trades": sum(fold["metrics"]["trades"] for fold in fold_results),
    }


def _rolling_oos(bars, strategies, target):
    folds = build_folds(len(bars), train_bars=FOLD_CONFIG["train_bars"],
                        test_bars=FOLD_CONFIG["test_bars"], step=FOLD_CONFIG["step_bars"])
    output = {"fold_configuration": FOLD_CONFIG, "strategies": {}}
    for family, strategy in strategies.items():
        fold_results, curves = [], []
        for fold in folds:
            fold_bars = bars[fold.train_start:fold.test_end]
            evaluation_start = fold.train_end - fold.train_start
            result = run(strategy, fold_bars, evaluation_start=evaluation_start,
                         evaluation_end=len(fold_bars) - 1)
            fold_payload = {
                "fold_id": fold.fold_id,
                "train_start": fold_bars[0]["timestamp"],
                "train_end": fold_bars[evaluation_start - 1]["timestamp"],
                "test_start": fold_bars[evaluation_start]["timestamp"],
                "test_end": fold_bars[-1]["timestamp"],
                "strategy_fingerprint": fingerprint(strategy),
                "fixed_parameters": strategy,
                "metrics": metrics(result, strategy["risk"]["initial_equity"]),
                "ending_position_open": result["ending_position_open"],
                "ending_unrealized_pnl": result["ending_unrealized_pnl"],
            }
            if any(not (fold_payload["test_start"] <= trade["entry_time"] <= fold_payload["test_end"])
                   for trade in result["trades"]):
                raise AssertionError("warmup trade leaked into test fold")
            fold_results.append(fold_payload)
            curves.append(result["equity_curve"])
        stitched = stitched_oos_equity(curves)
        strategy_dir = target / family
        strategy_dir.mkdir(parents=True, exist_ok=True)
        (strategy_dir / "folds.json").write_text(json.dumps(fold_results, indent=2) + "\n")
        (strategy_dir / "stitched_oos_equity.json").write_text(json.dumps({
            "interpretation": "chronological aggregation of independent flat-start fold curves",
            "points": stitched}, indent=2) + "\n")
        output["strategies"][family] = _fold_summary(fold_results)
    return output


def run_robustness(output_root=ROOT / "reports/robustness/aapl_v0_2_0"):
    manifest, bars, strategies = _load_inputs()
    baseline = _reproduce_baseline(bars, strategies)
    commit = _git_commit()
    run_id = f"{commit[:12]}-{manifest['processed_file_sha256'][:12]}"
    target = Path(output_root) / run_id
    target.mkdir(parents=True, exist_ok=True)
    costs = _cost_sensitivity(bars, strategies)
    rolling = _rolling_oos(bars, strategies, target)
    robustness_manifest = {
        "analysis": "fixed_parameter_robustness",
        "parameter_selection": "none",
        "strategies": [{"strategy_id": family, "version": strategy["strategy_version"],
                        "fingerprint": fingerprint(strategy)}
                       for family, strategy in strategies.items()],
        "dataset": {"dataset_id": manifest["dataset_id"],
                    "version": manifest["dataset_version"],
                    "checksum": manifest["processed_file_sha256"],
                    "symbol": manifest["symbol"], "timeframe": manifest["timeframe"],
                    "adjustment_method": manifest["adjustment_method"]},
        "cost_scenarios": list(COST_SCENARIOS), "fold_configuration": FOLD_CONFIG,
        "boundary_mode": BOUNDARY_MODE, "warmup_policy": WARMUP_POLICY,
        "git_commit": commit, "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_reproduction": baseline,
        "metric_audit": {
            "exposure_definition": "bars with an actual open position during any part of the bar divided by evaluation bars",
            "prior_report_exposure_status": "unreliable_before_engine_1.3.0",
            "other_historical_metrics_changed": False,
        },
    }
    (target / "robustness_manifest.json").write_text(
        json.dumps(robustness_manifest, indent=2) + "\n")
    (target / "cost_sensitivity.json").write_text(json.dumps(costs, indent=2) + "\n")
    (target / "rolling_oos_summary.json").write_text(json.dumps(rolling, indent=2) + "\n")
    print(target)
    return target


if __name__ == "__main__":
    run_robustness()
