import copy
import json
from pathlib import Path

from backtest.data import load_bars
from backtest.engine.core import run
from backtest.strategies import mean_reversion
from backtest.strategies.registry import get_strategy_logic
from backtest.strategy import fingerprint, load_strategy
from scripts.run_backtest import main as run_backtest

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"strategies/mean_reversion_001/v0.1.0/strategy.yaml"

def bars(): return load_bars(ROOT/"data/mean_reversion_demo.csv")

def test_registry_and_insufficient_window():
    strategy=load_strategy(PATH)
    assert get_strategy_logic(strategy) is mean_reversion
    assert mean_reversion.evaluate_entry(strategy,bars(),3) is False

def test_threshold_and_zero_std_fail_safe():
    strategy=load_strategy(PATH); stable=bars()[:5]
    assert mean_reversion.evaluate_entry(strategy,stable,4) is False
    neutral=copy.deepcopy(bars()); closes=[98,99,100,101,100]
    for bar,value in zip(neutral[:5],closes): bar["close"]=value
    assert mean_reversion.evaluate_entry(strategy,neutral,4) is False
    assert mean_reversion.evaluate_entry(strategy,bars(),5) is True

def test_no_future_leakage():
    strategy=load_strategy(PATH); fixture=bars(); before=mean_reversion.evaluate_entry(strategy,fixture,5)
    fixture[6].update({"open":1,"high":1000,"low":1,"close":999})
    assert before is True and mean_reversion.evaluate_entry(strategy,fixture,5) is True

def test_next_bar_entry_and_mean_exit_next_open():
    result=run(load_strategy(PATH),bars()); trade=result["trades"][0]
    assert trade["signal_time"] == "2024-01-06"
    assert trade["entry_time"] == "2024-01-07"
    assert trade["exit_time"] == "2024-01-09"
    assert trade["exit_reason"] == "strategy_exit"

def test_atr_stop_remains_shared_engine_responsibility():
    fixture=bars(); fixture[7]["low"]=70
    trade=run(load_strategy(PATH),fixture)["trades"][0]
    assert trade["exit_reason"] == "stop"

def test_fingerprint_provenance_and_all_existing_strategy_regressions():
    strategy=load_strategy(PATH); run_backtest(PATH)
    report=json.loads((ROOT/"reports/mean_reversion_001/backtest_result.json").read_text())
    assert report["strategy_fingerprint"] == fingerprint(strategy)
    paths=["breakout_trend_001/v0.1.0","pullback_trend_001/v0.1.0","breakout_001/v1.0.0"]
    for relative in paths:
        existing=load_strategy(ROOT/"strategies"/relative/"strategy.yaml")
        data=ROOT/"data"/(existing["dataset_id"]+".csv")
        assert run(existing,load_bars(data))["equity_curve"]
