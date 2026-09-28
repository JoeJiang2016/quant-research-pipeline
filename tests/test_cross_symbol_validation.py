import copy
import json
from pathlib import Path

import pytest

from backtest.experiments import load_experiment
from backtest.reconciliation import load_config
from backtest.strategy import fingerprint, load_strategy
from scripts import run_cross_symbol_validation as cross

ROOT = Path(__file__).resolve().parents[1]


def valid_manifest(symbol="MSFT"):
    return {
        "dataset_id": f"{symbol.lower()}_1d_yf_adjusted", "dataset_version": "1",
        "symbol": symbol, "asset_class": "equity", "country": "US",
        "timeframe": "1d", "start": "2015-05-26", "end": "2025-10-16",
        "processed_file_sha256": "a" * 64, "adjustment_method": "yfinance_auto_adjust",
        "provenance": {"provider_acquisition_id": "fixture"},
        "quality_summary": {"canonical_null_count": 0, "malformed_rows": 0,
                            "duplicate_timestamps": 0, "invalid_ohlc": 0,
                            "negative_volume": 0, "nan_or_infinity": 0,
                            "strictly_increasing": True},
    }


def record(symbol, strategy, value, trades=1):
    metrics = {"trades": trades, "total_return": value, "profit_factor": 1.0,
               "max_drawdown": abs(value) / 2, "sharpe": value * 10,
               "expectancy": value * 100}
    return {"symbol": symbol, "strategy_id": strategy, "strategy_version": "0.2.0",
            "strategy_fingerprint": cross.EXPECTED_FINGERPRINTS[strategy],
            "dataset_id": symbol.lower(), "dataset_version": "1",
            "dataset_checksum": "a" * 64, "experiment_fingerprint": "b" * 64,
            "is": {key: metrics[key] for key in metrics if key != "expectancy"},
            "oos": metrics}


def test_runner_orchestrates_existing_experiment_engine_only():
    assert cross.run_experiment.__module__ == "scripts.run_research_experiment"
    source = (ROOT / "scripts/run_cross_symbol_validation.py").read_text()
    assert "backtest.engine" not in source


def test_contracts_and_experiments_share_dates_costs_and_asset_metadata():
    for symbol in cross.COHORT[1:]:
        config = load_config(ROOT / f"config/data_sources/yfinance_{symbol.lower()}_daily.json")
        assert (config["symbol"], config["asset_class"], config["country"]) == (symbol, "equity", "US")
        assert config["start"] == cross.RESEARCH_WINDOW["start"]
        assert config["end_exclusive"] == "2025-10-17"
        experiment = load_experiment(ROOT / f"research/experiments/{symbol.lower()}_real_baseline_v1.yaml")
        assert experiment["evaluation"] == {"in_sample": cross.IS_WINDOW,
                                             "out_of_sample": cross.OOS_WINDOW}
        assert experiment["cost_sensitivity"]["scenarios"] == [{
            "name": "canonical_strategy_costs", "commission_multiplier": 1.0,
            "slippage_multiplier": 1.0}]


def test_invalid_and_missing_datasets_fail_closed(tmp_path):
    broken = valid_manifest()
    broken["quality_summary"]["duplicate_timestamps"] = 1
    with pytest.raises(ValueError, match="invalid"):
        cross.validate_dataset_manifest(broken, symbol="MSFT")
    with pytest.raises(FileNotFoundError, match="missing symbol dataset"):
        cross._manifest_for_experiment({"dataset": {"manifest_path": str(tmp_path / "missing.json")}})


def test_fingerprints_are_frozen_and_loading_does_not_mutate_parameters():
    for family, expected in cross.EXPECTED_FINGERPRINTS.items():
        strategy = load_strategy(ROOT / f"strategies/{family}/v0.2.0/strategy.yaml")
        before = copy.deepcopy(strategy)
        assert fingerprint(strategy) == expected
        assert strategy == before


def test_cross_symbol_aggregation_is_deterministic_and_retains_zero_trade_record():
    records = []
    for symbol_index, symbol in enumerate(cross.COHORT):
        for strategy_index, strategy in enumerate(cross.STRATEGIES):
            trades = 0 if symbol == "NVDA" and strategy == "mean_reversion_001" else 1
            records.append(record(symbol, strategy, (symbol_index - strategy_index) / 100,
                                  trades=trades))
    first = cross.aggregate_records(records)
    second = cross.aggregate_records(list(reversed(records)))
    assert first == second
    assert len(first["records"]) == 15
    assert any(item["oos"]["trades"] == 0 for item in first["records"])
    prohibited = {"rank", "score", "winner", "best", "approved", "rejected"}
    def keys(value):
        if isinstance(value, dict):
            return set(value).union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value), set())
        return set()
    assert not prohibited.intersection(keys(first))


def test_aapl_reproduction_check_detects_drift():
    strategies = []
    for strategy in cross.STRATEGIES:
        metrics = {key: 1 for key in cross.CORE_METRICS}
        strategies.append({"strategy_id": strategy,
                           "is_metrics": copy.deepcopy(metrics),
                           "oos_metrics": copy.deepcopy(metrics)})
    summary = {"strategies": strategies}
    assert cross._verify_aapl(summary, copy.deepcopy(summary)) is True
    changed = copy.deepcopy(summary)
    changed["strategies"][0]["oos_metrics"]["total_return"] = 2
    with pytest.raises(RuntimeError, match="reproduction failed"):
        cross._verify_aapl(summary, changed)
