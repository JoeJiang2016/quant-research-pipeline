import copy
import csv
import json
from datetime import date, timedelta
from pathlib import Path

import yaml

from backtest.datasets import import_dataset
from backtest.engine.core import run
from backtest.strategy import fingerprint, load_strategy
from scripts.run_research_experiment import (BOUNDARY_MODE, WARMUP_POLICY,
                                             evaluation_indices, run_experiment)

ROOT = Path(__file__).resolve().parents[1]


def breakout_strategy():
    strategy = copy.deepcopy(load_strategy(
        ROOT / "strategies/breakout_trend_001/v0.1.0/strategy.yaml"))
    strategy["entry"]["lookback_bars"] = 2
    strategy["exit"].update({"atr_period": 2, "stop_atr_multiple": 10.0,
                             "take_profit_atr_multiple": 0.5})
    strategy["execution"].update({"commission_per_trade": 0, "slippage_bps": 0})
    return strategy


def bar(day, close, *, open_=None, high=None, low=None):
    return {"timestamp": f"2024-01-{day:02d}", "open": open_ or close,
            "high": high if high is not None else close + 0.2,
            "low": low if low is not None else close - 0.2,
            "close": close, "volume": 1000.0, "symbol": "DEMO"}


def fixture_bars():
    return [bar(1, 10), bar(2, 10), bar(3, 12, high=12.2),
            bar(4, 12.5, open_=12.1, high=14, low=12),
            bar(5, 11), bar(6, 11), bar(7, 11)]


def test_evaluation_config_selects_only_active_curve_and_trades():
    bars = fixture_bars()
    start, end = evaluation_indices(bars, {"start": "2024-01-03", "end": "2024-01-04"})
    result = run(breakout_strategy(), bars, evaluation_start=start, evaluation_end=end)
    assert [point["timestamp"] for point in result["equity_curve"]] == [
        "2024-01-03", "2024-01-04"]
    assert result["trades"][0]["signal_time"] == "2024-01-03"
    assert result["trades"][0]["entry_time"] == "2024-01-04"
    assert all("2024-01-03" <= trade["entry_time"] <= "2024-01-04"
               for trade in result["trades"])


def test_historical_warmup_available_but_pre_boundary_signal_cannot_fill():
    bars = fixture_bars()
    # Starting on the signal bar can use bars 1-2 as lookback and fill on bar 4.
    warm = run(breakout_strategy(), bars, evaluation_start=2, evaluation_end=3)
    assert warm["trades"] and warm["trades"][0]["entry_time"] == "2024-01-04"
    # Starting after that signal initializes with no pending order from bar 3.
    flat = run(breakout_strategy(), bars, evaluation_start=3, evaluation_end=4)
    assert flat["equity_curve"][0]["equity"] == 100000
    assert all(trade["signal_time"] >= "2024-01-04" for trade in flat["trades"])


def test_is_position_and_pending_order_do_not_carry_to_oos():
    bars = fixture_bars()
    is_result = run(breakout_strategy(), bars, evaluation_start=0, evaluation_end=3)
    oos_result = run(breakout_strategy(), bars, evaluation_start=4, evaluation_end=6)
    assert is_result["equity_curve"][-1]["timestamp"] == "2024-01-04"
    assert oos_result["equity_curve"][0] == {"timestamp": "2024-01-05", "equity": 100000}
    # A signal on the last IS bar can never schedule an OOS fill because end is inclusive.
    pending_fixture = [bar(1, 10), bar(2, 10), bar(3, 12), bar(4, 12)]
    is_pending = run(breakout_strategy(), pending_fixture, evaluation_start=0, evaluation_end=2)
    oos_after = run(breakout_strategy(), pending_fixture, evaluation_start=3, evaluation_end=3)
    assert is_pending["trades"] == [] and oos_after["trades"] == []
    assert oos_after["equity_curve"][0]["equity"] == 100000


def test_future_bars_cannot_change_earlier_evaluation():
    bars = fixture_bars()
    first = run(breakout_strategy(), bars, evaluation_start=2, evaluation_end=3)
    changed = copy.deepcopy(bars)
    changed[4].update({"open": 999, "high": 1000, "low": 998, "close": 999})
    second = run(breakout_strategy(), changed, evaluation_start=2, evaluation_end=3)
    assert first == second


def test_boundary_constants_and_frozen_v02_fingerprints():
    assert BOUNDARY_MODE == "flat_start"
    assert "indicators_only" in WARMUP_POLICY
    for family in ("breakout_trend_001", "pullback_trend_001", "mean_reversion_001"):
        strategy = load_strategy(ROOT / "strategies" / family / "v0.2.0/strategy.yaml")
        assert fingerprint(strategy) == fingerprint(copy.deepcopy(strategy))


def test_six_segment_results_share_provenance_and_summary_has_no_selection(tmp_path):
    source = tmp_path / "aapl_fixture.csv"
    fields = ["Date", "Open", "High", "Low", "Close", "Volume"]
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for index in range(60):
            stamp = date(2024, 1, 1) + timedelta(days=index)
            close = 100 + index * 0.2 + (2 if index % 9 == 0 else 0)
            writer.writerow({"Date": stamp.isoformat(), "Open": close - 0.1,
                             "High": close + 1, "Low": close - 1,
                             "Close": close, "Volume": 1000 + index})
    imported = import_dataset(
        source, dataset_id="aapl_test", version="2", symbol="AAPL",
        timeframe="1d", source_timezone=None, timestamp_semantics="session_date",
        source="offline fixture", price_adjustment="provider_adjusted",
        adjustment_method="test", asset_class="equity", country="US",
        column_mapping={"timestamp": "Date", "open": "Open", "high": "High",
                        "low": "Low", "close": "Close", "volume": "Volume"},
        output_root=tmp_path / "data")
    spec = {
        "experiment_id": "offline_boundary_test", "experiment_version": "1.0.0",
        "description": "offline boundary regression",
        "dataset": {"dataset_id": "aapl_test",
                    "manifest_path": str(imported["manifest_path"])},
        "strategies": [{"strategy_id": family, "strategy_version": "0.2.0"}
                       for family in ("breakout_trend_001", "pullback_trend_001",
                                      "mean_reversion_001")],
        "research_window": {"start": "2024-01-01", "end": "2024-02-29"},
        "evaluation": {
            "in_sample": {"start": "2024-01-01", "end": "2024-02-09"},
            "out_of_sample": {"start": "2024-02-10", "end": "2024-02-29"}},
        "walk_forward": {"enabled": False, "train_bars": 1,
                         "test_bars": 1, "step_bars": 1},
        "cost_sensitivity": {"enabled": False, "scenarios": [{
            "name": "canonical", "commission_multiplier": 1,
            "slippage_multiplier": 1}]},
    }
    spec_path = tmp_path / "experiment.yaml"
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    target = run_experiment(spec_path, tmp_path / "reports")
    checksums = set()
    for family in ("breakout_trend_001", "pullback_trend_001", "mean_reversion_001"):
        is_result = json.loads((target / family / "is_result.json").read_text())
        oos_result = json.loads((target / family / "oos_result.json").read_text())
        assert is_result["strategy_fingerprint"] == oos_result["strategy_fingerprint"]
        assert is_result["parameter_snapshot"] == oos_result["parameter_snapshot"]
        checksums.update((is_result["dataset_checksum"], oos_result["dataset_checksum"]))
        assert all(trade["entry_time"] <= "2024-02-09" for trade in is_result["trade_log"])
        assert all(trade["entry_time"] >= "2024-02-10" for trade in oos_result["trade_log"])
    assert checksums == {imported["manifest"]["processed_file_sha256"]}
    summary = json.loads((target / "baseline_summary.json").read_text())
    prohibited = {"rank", "score", "winner", "best", "approved", "rejected"}
    def keys(value):
        if isinstance(value, dict):
            return set(value).union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value), set())
        return set()
    assert not prohibited.intersection(keys(summary))
