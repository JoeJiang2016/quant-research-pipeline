import copy
import json

import pytest

from backtest.data import load_bars
from backtest.engine.core import metrics, run
from backtest.splits import DatasetSplit, split_bars
from backtest.validation import validate_result, validate_strategy


BASE = {
    "strategy_id": "test_breakout", "strategy_version": "1", "dataset_id": "test",
    "universe": ["TEST"], "timeframe": "1d",
    "execution": {"signal_time": "bar_close", "fill_time": "next_bar_open", "order_type": "market", "commission_per_trade": 1, "slippage_bps": 0},
    "entry": {"rule": "close_breakout", "lookback_bars": 2, "direction": "long", "volume_multiplier": 0},
    "exit": {"atr_period": 2, "stop_atr_multiple": .4, "take_profit_atr_multiple": 1},
    "risk": {"initial_equity": 10000, "risk_per_trade_pct": .01},
}


def bars(exit_high=108, entry_low=102.1, exit_low=102.1):
    return [
        {"timestamp": "2024-01-01", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
        {"timestamp": "2024-01-02", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
        {"timestamp": "2024-01-03", "open": 100, "high": 102, "low": 99, "close": 102, "volume": 1},
        {"timestamp": "2024-01-04", "open": 103, "high": 104, "low": entry_low, "close": 103, "volume": 1},
        {"timestamp": "2024-01-05", "open": 103, "high": exit_high, "low": exit_low, "close": 105, "volume": 1},
    ]


def test_schema_validation_accepts_complete_candidate():
    validate_strategy(BASE)


def test_schema_rejects_unknown_or_invalid_parameter():
    invalid = copy.deepcopy(BASE); invalid["entry"]["lookback_bars"] = 1
    with pytest.raises(ValueError): validate_strategy(invalid)
    invalid = copy.deepcopy(BASE); invalid["unexpected"] = True
    with pytest.raises(ValueError): validate_strategy(invalid)


def test_entry_signal_fills_next_open_with_risk_sized_position():
    trade = run(BASE, bars())["trades"][0]
    assert (trade["signal_time"], trade["entry_time"], trade["quantity"]) == ("2024-01-03", "2024-01-04", 100)


def test_exit_take_profit_is_logged():
    assert run(BASE, bars())["trades"][0]["exit_reason"] == "take_profit"


def test_stop_loss_wins_same_bar_collision():
    strategy = copy.deepcopy(BASE); strategy["exit"]["take_profit_atr_multiple"] = .4
    assert run(strategy, bars(entry_low=102))["trades"][0]["exit_reason"] == "stop"


def test_future_bar_does_not_change_past_signal_or_fill():
    original = run(BASE, bars())["trades"][0]
    changed = run(BASE, bars(exit_high=10000))["trades"][0]
    assert (original["signal_time"], original["entry_time"], original["entry_price"]) == (changed["signal_time"], changed["entry_time"], changed["entry_price"])


def test_commission_slippage_and_trade_log_equity_are_consistent():
    strategy = copy.deepcopy(BASE); strategy["execution"].update({"commission_per_trade": 2, "slippage_bps": 10})
    result = run(strategy, bars())
    assert result["commission"] == sum(t["commission"] for t in result["trades"])
    assert result["slippage"] > 0
    assert result["equity_curve"][-1]["equity"] == pytest.approx(10000 + sum(t["pnl"] for t in result["trades"]))


def test_zero_trades_has_consistent_metrics_and_curve():
    flat = bars(); [bar.update({"high": 101, "low": 99, "close": 100}) for bar in flat]
    result = run(BASE, flat); summary = metrics(result, 10000)
    assert result["trades"] == [] and summary["trades"] == 0 and len(result["equity_curve"]) == len(flat)


def test_no_duplicate_order_while_position_is_open():
    result = run(BASE, bars())
    assert len(result["trades"]) == 1


def test_insufficient_lookback_history_is_rejected():
    with pytest.raises(ValueError, match="insufficient history"):
        run(BASE, bars()[:3])


def test_ohlcv_loader_rejects_missing_data_and_malformed_timestamps(tmp_path):
    missing = tmp_path / "missing.csv"; missing.write_text("timestamp,open,high,low,close,volume\n2024-01-01,1,,1,1,1\n")
    with pytest.raises(ValueError): load_bars(missing)
    malformed = tmp_path / "time.csv"; malformed.write_text("timestamp,open,high,low,close,volume\nnot-a-date,1,1,1,1,1\n")
    with pytest.raises(ValueError): load_bars(malformed)


def test_split_is_deterministic_and_oos_cannot_include_training_bars():
    source = bars()
    in_sample = split_bars(source, "2024-01-03", "2024-01-04", DatasetSplit.IN_SAMPLE)
    out_sample = split_bars(source, "2024-01-03", "2024-01-04", DatasetSplit.OUT_OF_SAMPLE)
    assert in_sample[-1]["timestamp"] == "2024-01-03"
    assert out_sample[0]["timestamp"] == "2024-01-04"
    assert {b["timestamp"] for b in in_sample}.isdisjoint({b["timestamp"] for b in out_sample})


def test_result_schema_and_trade_log_invariants_reject_invalid_result():
    result = {"strategy_id":"x", "strategy_version":"1", "dataset_id":"d", "period":{"start":"2024-01-01", "end":"2024-01-02"}, "metrics":{"trades":0,"total_return":0,"commission":0,"slippage":0}, "equity_curve":[{"timestamp":"2024-01-01","equity":1}], "trade_log":[], "parameter_snapshot":{}, "execution_assumptions":{"signal_time":"bar_close","fill_time":"next_bar_open","same_bar_stop_target":"stop_first"}, "reproducibility":{"git_commit":"abc", "data_version":"d.csv", "data_checksum_sha256":"a"*64, "timestamp":"2024-01-01T00:00:00+00:00", "engine_version":"1"}}
    validate_result(result)
    result["trade_log"] = [{"signal_time":"2024-01-02", "entry_time":"2024-01-01", "exit_time":"2024-01-01", "side":"long", "quantity":1, "entry_price":1, "exit_price":1, "exit_reason":"stop", "pnl":0, "commission":0}]
    with pytest.raises(ValueError): validate_result(result)
