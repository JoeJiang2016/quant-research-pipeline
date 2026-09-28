"""Rolling OOS robustness for the revealed, precommitted Phase 3D-3 cohort."""
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

from backtest.datasets import load_dataset
from backtest.engine.core import metrics, run
from backtest.strategy import fingerprint, load_strategy
from backtest.walk_forward import build_folds
from scripts.run_aapl_robustness import FOLD_CONFIG
from scripts.run_cross_symbol_rolling import percentile, stitch_symbol_curves
from scripts.run_cross_symbol_validation import EXPECTED_FINGERPRINTS, STRATEGIES
from scripts.run_holdout_validation import (
    CANONICAL_COSTS, COHORT_PATH, SEEN_PILOT, file_sha256,
    validate_frozen_cohort,
)

PHASE3D3_COMMIT = "aa4bfd3705e0dff1d6fe830a1c052dc79434b563"
REVEAL_STATUS = "revealed_holdout_after_3d3"
INSUFFICIENT_SYMBOLS = ("CTVA", "SOLV")
EXPECTED_DATASETS = {
    "T": ("t_1d_yf_adjusted", "0af3302b39aa9a6dbd43a3a10c5c09c6684acd870e120634ff330bf3666d69b6"),
    "XEL": ("xel_1d_yf_adjusted", "395785275043d0912a3ecc2cf03b1e05f2b1d3a803affdfd7737d8abd3422d4e"),
    "SYK": ("syk_1d_yf_adjusted", "121215f89a6abaa4dc71f23cb2f73182dec256a8ed7082716e7c93b3d6eff1f9"),
    "PCAR": ("pcar_1d_yf_adjusted", "bdc7b7ce9f64402e0b15f4a9c2a4ad18f5aa787b64105205e2f58688100f6960"),
    "VTR": ("vtr_1d_yf_adjusted", "118fb590faeb4cf5196a42e60cfdb947abcedddebcc775b5049e389c4ef9677c"),
    "SPGI": ("spgi_1d_yf_adjusted", "00f0a16bd1dfdada757efc0a5a0063a241f5032f715a9ef348d621c6430b2bea"),
    "LYV": ("lyv_1d_yf_adjusted", "baa7102ff0dfd3693fb4635e9b35e8e8a8e70ce59a848f2397218403d10df446"),
    "MAA": ("maa_1d_yf_adjusted", "2da8d7a3c2fe181459e887c82d504b7abd048d36f77db399471537da215f763b"),
    "RMD": ("rmd_1d_yf_adjusted", "9572f0e6e8dbef2a304e59f688cb14254354ad5925f68c232a88ebb5afa48f01"),
    "IT": ("it_1d_yf_adjusted", "3bc0bdea570d671f827ac2410f062cfd135d9b224f8b96c294145012e94d7e2c"),
    "VMC": ("vmc_1d_yf_adjusted", "de1259d477a83d4162a5f9ab25cec18b8f6d8f1c7287761fcaf5da7da0af8574"),
    "HSIC": ("hsic_1d_yf_adjusted", "3579e64d9f1e43fccfb3272fdc67143e53148a7be4499a7acca05345a6f12d4f"),
    "FTNT": ("ftnt_1d_yf_adjusted", "931fdc5bc657a9408e126e69b5a3104bb0cbcbe589185f7eb991b4a51bd0809e"),
    "LKQ": ("lkq_1d_yf_adjusted", "ba821f31e25c3cdf64e9f83fd5fbecbc25a42269bee4fa374282d2a268fec1fd"),
    "IFF": ("iff_1d_yf_adjusted", "df20e07eefd889795e27fdc5826ed3eb5c3ce22f9e26684c0036c3b54a619094"),
    "NSC": ("nsc_1d_yf_adjusted", "782e0e12f4bde42d50460f488c79da1a7e40f7885b642d09291a4885b765e374"),
    "ALB": ("alb_1d_yf_adjusted", "55747a6956f0ec318c7c84ca87befdcff02a47c2e3359f73ca0ae65045174f10"),
    "AMT": ("amt_1d_yf_adjusted", "89a0aab2da9f1567aa5157c093f42b85120fad6703d0d937d20f313801689f67"),
    "INTU": ("intu_1d_yf_adjusted", "5f8b22ea553a9288ccd6c21dc3217ae8fbeeb584c2d9efd7bab1136da893048d"),
    "ON": ("on_1d_yf_adjusted", "564ead588e3222779a9d7ef3461f9f53dcac59ec1a8dcefe11e53f0095a32bab"),
    "EMN": ("emn_1d_yf_adjusted", "f113a2c98fbd47aad4a24375ddd3136a10c66c3419c21a6d92b8e51d30af0f66"),
    "ORLY": ("orly_1d_yf_adjusted", "bb4247fab5c60e061e4d8d7a7725e78da29134b8fd64b58c5e3be9efd472ba71"),
    "EMR": ("emr_1d_yf_adjusted", "5dedde65b4cfb74222e8822153cf664e6ab9425baf899cd5eeaa7044160dbb5b"),
    "APTV": ("aptv_1d_yf_adjusted", "047529625ff0b000f35019e47c9560444577e5c18d2348c6bc35e43a294fb277"),
    "HST": ("hst_1d_yf_adjusted", "067026fc1492a46950434eba9ce616e4c6750c82fcc71bd526dcce714f44bb6d"),
    "PCG": ("pcg_1d_yf_adjusted", "91ff32b9bd97e160c052720a84f0f4630931f9e4f032ebeee5283274ebd43a48"),
    "DECK": ("deck_1d_yf_adjusted", "cf89e8bf286fddb4a3753a45cc09096f9a1a498ab3ff2b50bd18da2b49a8faeb"),
    "ATO": ("ato_1d_yf_adjusted", "b465d11f6fe6f52afc7d9ddbac35117d77f18b108e273c5e6771ebc750bace6a"),
}


def phase3d3_status_path():
    candidates = sorted((ROOT / "reports/cross_symbol/holdout_v1").glob(
        f"{PHASE3D3_COMMIT[:12]}-*/acquisition_status.json"))
    if not candidates:
        raise FileNotFoundError("Phase 3D-3 acquisition status is required")
    return candidates[0]


def verify_inputs():
    cohort = validate_frozen_cohort()
    statuses = json.loads(phase3d3_status_path().read_text())["symbols"]
    if [item["symbol"] for item in statuses] != cohort["selected_symbols"]:
        raise RuntimeError("Phase 3D-3 status membership/order differs from frozen cohort")
    if {item["symbol"] for item in statuses if item["status"] == "insufficient_history"} != set(INSUFFICIENT_SYMBOLS):
        raise RuntimeError("insufficient-history membership changed")
    valid = [item for item in statuses if item["status"] == "valid"]
    if len(valid) != 28 or {item["symbol"] for item in valid} != set(EXPECTED_DATASETS):
        raise RuntimeError("valid holdout membership changed")
    datasets = {}
    for item in valid:
        symbol = item["symbol"]
        expected_id, expected_checksum = EXPECTED_DATASETS[symbol]
        manifest = json.loads(Path(item["dataset_manifest_path"]).read_text())
        identity = (manifest["dataset_id"], manifest["processed_file_sha256"])
        if identity != (expected_id, expected_checksum) or identity != (
                item["dataset_id"], item["dataset_checksum"]):
            raise RuntimeError(f"{symbol} dataset identity drift detected")
        if (manifest["asset_class"], manifest["country"], manifest["timeframe"]) != (
                "equity", "US", "1d"):
            raise RuntimeError(f"{symbol} dataset metadata drift detected")
        bars = load_dataset(manifest["processed_path"], symbol=symbol,
                            timeframe=manifest["timeframe"],
                            timestamp_semantics=manifest["timestamp_semantics"])
        if len(bars) != 2616:
            raise RuntimeError(f"{symbol} expected 2616 bars, got {len(bars)}")
        datasets[symbol] = (manifest, bars)
    strategies = {name: load_strategy(ROOT / f"strategies/{name}/v0.2.0/strategy.yaml")
                  for name in STRATEGIES}
    if {name: fingerprint(value) for name, value in strategies.items()} != EXPECTED_FINGERPRINTS:
        raise RuntimeError("strategy fingerprint drift detected")
    if any({"commission_per_trade": value["execution"]["commission_per_trade"],
            "slippage_bps": value["execution"]["slippage_bps"]} != CANONICAL_COSTS
           for value in strategies.values()):
        raise RuntimeError("canonical costs drift detected")
    changed = subprocess.run(["git", "diff", "--quiet", PHASE3D3_COMMIT, "--", "strategies"],
                             cwd=ROOT).returncode
    if changed:
        raise RuntimeError("strategy files changed since Phase 3D-3")
    return cohort, statuses, datasets, strategies


def summarize_symbol_folds(records):
    returns = [item["metrics"]["total_return"] for item in records]
    pfs = [item["metrics"]["profit_factor"] for item in records
           if item["metrics"]["profit_factor"] is not None]
    return {"fold_count": len(records),
        "positive_return_folds": sum(value > 0 for value in returns),
        "negative_return_folds": sum(value < 0 for value in returns),
        "zero_return_folds": sum(value == 0 for value in returns),
        "median_return": statistics.median(returns),
        "return_25th_percentile": percentile(returns, .25),
        "return_75th_percentile": percentile(returns, .75),
        "min_return": min(returns), "max_return": max(returns),
        "median_profit_factor": statistics.median(pfs) if pfs else None,
        "median_sharpe": statistics.median(item["metrics"]["sharpe"] for item in records),
        "worst_max_drawdown": max(item["metrics"]["max_drawdown"] for item in records),
        "total_trades": sum(item["metrics"]["trades"] for item in records)}


def positive_fold_distribution(symbol_summaries):
    output = {}
    for strategy_id in STRATEGIES:
        counts = {f"{number}_of_7": 0 for number in range(8)}
        for summaries in symbol_summaries.values():
            counts[f"{summaries[strategy_id]['positive_return_folds']}_of_7"] += 1
        output[strategy_id] = counts
    return output


def aggregate_cells(records):
    output = {}
    for strategy_id in STRATEGIES:
        subset = [item for item in records if item["strategy_id"] == strategy_id]
        returns = [item["metrics"]["total_return"] for item in subset]
        pfs = [item["metrics"]["profit_factor"] for item in subset
               if item["metrics"]["profit_factor"] is not None]
        output[strategy_id] = {"cell_count": len(subset),
            "positive_cells": sum(value > 0 for value in returns),
            "negative_cells": sum(value < 0 for value in returns),
            "zero_cells": sum(value == 0 for value in returns),
            "positive_percentage": 100 * sum(value > 0 for value in returns) / len(returns),
            "median_return": statistics.median(returns),
            "return_25th_percentile": percentile(returns, .25),
            "return_75th_percentile": percentile(returns, .75),
            "min_return": min(returns), "max_return": max(returns),
            "median_profit_factor": statistics.median(pfs) if pfs else None,
            "median_sharpe": statistics.median(item["metrics"]["sharpe"] for item in subset),
            "worst_max_drawdown": max(item["metrics"]["max_drawdown"] for item in subset),
            "total_trades": sum(item["metrics"]["trades"] for item in subset)}
    return output


def chronological_breadth(records):
    output = {}
    for strategy_id in STRATEGIES:
        rows = []
        for fold_id in [f"fold_{number:03d}" for number in range(1, 8)]:
            subset = [item for item in records
                      if item["strategy_id"] == strategy_id and item["fold_id"] == fold_id]
            boundaries = {(item["test_start"], item["test_end"]) for item in subset}
            if len(subset) != 28 or len(boundaries) != 1:
                raise RuntimeError(f"incomplete or misaligned breadth: {strategy_id} {fold_id}")
            values = [item["metrics"]["total_return"] for item in subset]
            rows.append({"fold_id": fold_id, "test_start": subset[0]["test_start"],
                "test_end": subset[0]["test_end"],
                "positive_symbols": sum(value > 0 for value in values),
                "negative_symbols": sum(value < 0 for value in values),
                "zero_symbols": sum(value == 0 for value in values),
                "median_return": statistics.median(values),
                "return_25th_percentile": percentile(values, .25),
                "return_75th_percentile": percentile(values, .75)})
        output[strategy_id] = rows
    return output


def _git_commit():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def run_holdout_rolling(output_root=ROOT / "reports/cross_symbol/holdout_rolling_v1"):
    cohort, statuses, datasets, strategies = verify_inputs()
    folds = build_folds(2616, train_bars=756, test_bars=252, step=252, anchored=False)
    if len(folds) != 7 or folds[-1].test_end != 2520:
        raise RuntimeError("rolling fold structure differs from frozen configuration")
    commit = _git_commit(); cohort_checksum = file_sha256(COHORT_PATH)
    target = Path(output_root) / f"{commit[:12]}-{cohort_checksum[:12]}"
    target.mkdir(parents=True, exist_ok=True)
    records, symbol_summaries = [], {}
    for symbol, (manifest, bars) in datasets.items():
        symbol_summaries[symbol] = {}
        for strategy_id, strategy in strategies.items():
            fold_records, curves = [], []
            for fold in folds:
                fold_bars = bars[fold.train_start:fold.test_end]
                evaluation_start = fold.train_end - fold.train_start
                result = run(strategy, fold_bars, evaluation_start=evaluation_start,
                             evaluation_end=len(fold_bars) - 1)
                values = metrics(result, strategy["risk"]["initial_equity"])
                record = {"symbol": symbol, "strategy_id": strategy_id,
                    "strategy_version": strategy["strategy_version"],
                    "strategy_fingerprint": fingerprint(strategy),
                    "dataset_id": manifest["dataset_id"],
                    "dataset_checksum": manifest["processed_file_sha256"],
                    "fold_id": fold.fold_id, "train_start": fold_bars[0]["timestamp"],
                    "train_end": fold_bars[evaluation_start - 1]["timestamp"],
                    "test_start": fold_bars[evaluation_start]["timestamp"],
                    "test_end": fold_bars[-1]["timestamp"],
                    "trade_count": values["trades"], "total_return": values["total_return"],
                    "win_rate": values["win_rate"], "expectancy": values["expectancy"],
                    "profit_factor": values["profit_factor"], "max_drawdown": values["max_drawdown"],
                    "sharpe": values["sharpe"], "sortino": values["sortino"],
                    "cagr": values["cagr"], "commission": values["commission"],
                    "slippage": values["slippage"], "metrics": values,
                    "ending_position_open": result["ending_position_open"],
                    "ending_unrealized_pnl": result["ending_unrealized_pnl"]}
                if any(not (record["test_start"] <= trade["entry_time"] <= record["test_end"])
                           for trade in result["trades"]):
                    raise AssertionError("warmup trade leaked into OOS fold")
                fold_records.append(record); records.append(record)
                curves.append({"symbol": symbol, "curve": result["equity_curve"]})
            strategy_dir = target / symbol / strategy_id
            strategy_dir.mkdir(parents=True, exist_ok=True)
            (strategy_dir / "folds.json").write_text(json.dumps(fold_records, indent=2) + "\n")
            stitched = stitch_symbol_curves(curves)
            stitched["interpretation"] = "independent flat-start OOS folds for one symbol; not continuous compounding"
            (strategy_dir / "stitched_oos_equity.json").write_text(json.dumps(stitched, indent=2) + "\n")
            symbol_summaries[symbol][strategy_id] = summarize_symbol_folds(fold_records)
    if len(records) != 588:
        raise RuntimeError(f"expected 588 evaluation cells, got {len(records)}")
    distribution = positive_fold_distribution(symbol_summaries)
    aggregate = aggregate_cells(records); breadth = chronological_breadth(records)
    (target / "per_symbol_summary.json").write_text(json.dumps(symbol_summaries, indent=2) + "\n")
    (target / "positive_fold_distribution.json").write_text(json.dumps(distribution, indent=2) + "\n")
    (target / "aggregate_summary.json").write_text(json.dumps(aggregate, indent=2) + "\n")
    (target / "fold_breadth.json").write_text(json.dumps(breadth, indent=2) + "\n")
    manifest_out = {"analysis": "fixed_parameter_holdout_rolling_oos_robustness",
        "cohort_id": cohort["cohort_id"], "cohort_status": REVEAL_STATUS,
        "secondary_robustness_evaluation": True,
        "phase3d3_results_were_viewed_after_strategy_freeze": True,
        "no_tuning_since_phase3d3": {"strategy_parameter_change": False,
            "cost_change": False, "universe_selection_change": False,
            "symbol_replacement": False},
        "valid_symbols": list(datasets), "insufficient_history_symbols": list(INSUFFICIENT_SYMBOLS),
        "seen_pilot_cohort_excluded": list(SEEN_PILOT),
        "datasets": {symbol: {"dataset_id": values[0]["dataset_id"],
            "checksum": values[0]["processed_file_sha256"]} for symbol, values in datasets.items()},
        "strategies": EXPECTED_FINGERPRINTS, "canonical_costs": CANONICAL_COSTS,
        "fold_configuration": FOLD_CONFIG, "complete_folds_per_symbol": 7,
        "excluded_tail_bars": 96, "cell_count_per_strategy": 196,
        "total_evaluation_cells": 588, "boundary_mode": "flat_start",
        "parameter_selection": "none", "fixed_oos_combined_with_rolling_oos": False,
        "phase3d3_fixed_oos_reference": str(phase3d3_status_path().parent),
        "git_commit": commit, "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "limitations": [
            "Phase 3D-3 fixed OOS results were already viewed; this is not a pristine unseen test.",
            "The modern symbol snapshot retains survivorship and constituent-history bias.",
            "Symbols and time windows are correlated; 196 cells are not independent samples.",
            "No regime labels or statistical significance claims are produced."]}
    (target / "manifest.json").write_text(json.dumps(manifest_out, indent=2) + "\n")
    print(target); return target


if __name__ == "__main__":
    run_holdout_rolling()
