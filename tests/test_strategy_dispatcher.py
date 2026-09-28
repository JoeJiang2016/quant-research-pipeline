import copy
import json
from pathlib import Path
import pytest

from backtest.data import load_bars
from backtest.engine.core import run
from backtest.strategies import breakout
from backtest.strategies.registry import get_strategy_logic
from backtest.strategy import fingerprint, load_strategy
from scripts.run_backtest import main as run_backtest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "strategies/breakout_trend_001/v0.1.0/strategy.yaml"
HISTORICAL = ROOT / "strategies/breakout_001/v1.0.0/strategy.yaml"


def spec():
    return {
        "strategy_type": "breakout",
        "entry": {"rule": "close_breakout", "lookback_bars": 2, "direction": "long"},
        "exit": {"atr_period": 2, "stop_atr_multiple": 2, "take_profit_atr_multiple": 1},
        "risk": {"initial_equity": 10000, "risk_per_trade_pct": .01},
        "execution": {"commission_per_trade": 1, "slippage_bps": 0},
    }


def fixture(signal_close=102, signal_high=103):
    values=[(100,101,99,100),(100,101,99,100),(100,signal_high,99,signal_close),(102,103,101,102),(102,106,101,105)]
    return [{"timestamp":str(i),"open":o,"high":h,"low":l,"close":c,"volume":1} for i,(o,h,l,c) in enumerate(values)]


def test_dispatcher_resolves_breakout_and_unknown_fails_fast():
    assert get_strategy_logic(spec()) is breakout
    unknown=spec(); unknown["strategy_type"]="unknown"
    with pytest.raises(ValueError, match="unknown strategy type"): get_strategy_logic(unknown)


def test_breakout_excludes_current_bar_and_no_breakout_has_no_signal():
    strategy=spec(); bars=fixture()
    assert breakout.evaluate_entry(strategy,bars,2) is True  # current high=103 is excluded
    bars=fixture(signal_close=101,signal_high=110)
    assert breakout.evaluate_entry(strategy,bars,2) is False


def test_signal_fills_next_bar_and_strategy_logic_has_no_state_side_effects():
    strategy=spec(); bars=fixture(); original=copy.deepcopy(bars)
    assert breakout.evaluate_entry(strategy,bars,2) is True
    assert bars == original
    trade=run(strategy,bars)["trades"][0]
    assert trade["signal_time"] == "2"
    assert trade["entry_time"] == "3"
    assert trade["exit_reason"] == "take_profit"


def test_candidate_fingerprint_and_result_provenance_and_historical_regression():
    candidate=load_strategy(CANDIDATE); historical=load_strategy(HISTORICAL)
    assert len(fingerprint(candidate)) == 64
    assert run(historical,load_bars(ROOT/"data/demo_ohlcv.csv"))["equity_curve"]
    run_backtest(CANDIDATE)
    result=json.loads((ROOT/"reports/breakout_trend_001/backtest_result.json").read_text())
    assert (result["strategy_id"],result["strategy_version"],result["strategy_fingerprint"]) == ("breakout_trend_001","0.1.0",fingerprint(candidate))
