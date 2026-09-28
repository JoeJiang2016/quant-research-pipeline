import copy
import json
from pathlib import Path

from backtest.data import load_bars
from backtest.engine.core import run
from backtest.strategies import pullback
from backtest.strategies.registry import get_strategy_logic
from backtest.strategy import fingerprint, load_strategy
from scripts.run_backtest import main as run_backtest

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"strategies/pullback_trend_001/v0.1.0/strategy.yaml"


def bars():
    return load_bars(ROOT/"data/pullback_demo.csv")


def test_registry_resolves_pullback():
    assert get_strategy_logic(load_strategy(PATH)) is pullback


def test_no_trend_no_entry():
    strategy=load_strategy(PATH); flat=copy.deepcopy(bars())
    for bar in flat: bar["close"]=bar["open"]=100; bar["high"]=101; bar["low"]=99
    assert pullback.evaluate_entry(strategy,flat,6) is False


def test_trend_without_pullback_has_no_entry():
    strategy=load_strategy(PATH); rising=bars()[:7]
    rising[5].update({"open":104,"high":106,"low":103.5,"close":105})
    rising[6].update({"open":105,"high":107,"low":104.5,"close":106})
    assert pullback.evaluate_entry(strategy,rising,6) is False


def test_pullback_without_confirmation_has_no_entry():
    strategy=load_strategy(PATH); fixture=bars()
    fixture[6]["close"]=102.9
    assert pullback.evaluate_entry(strategy,fixture,6) is False


def test_pullback_confirmation_signals_without_future_leakage():
    strategy=load_strategy(PATH); fixture=bars(); snapshot=copy.deepcopy(fixture[:7])
    assert pullback.evaluate_entry(strategy,fixture,6) is True
    fixture[7].update({"open":1,"high":1000,"low":1,"close":999})
    assert pullback.evaluate_entry(strategy,fixture,6) is True
    assert fixture[:7] == snapshot


def test_signal_executes_next_bar_and_provenance_is_canonical():
    strategy=load_strategy(PATH); result=run(strategy,bars()); assert result["trades"]
    trade=result["trades"][0]
    assert trade["signal_time"] == "2024-01-07"
    assert trade["entry_time"] == "2024-01-08"
    run_backtest(PATH)
    report=json.loads((ROOT/"reports/pullback_trend_001/backtest_result.json").read_text())
    assert report["strategy_fingerprint"] == fingerprint(strategy)


def test_breakout_families_still_dispatch_and_run():
    for path in [ROOT/"strategies/breakout_trend_001/v0.1.0/strategy.yaml",ROOT/"strategies/breakout_001/v1.0.0/strategy.yaml"]:
        strategy=load_strategy(path)
        assert get_strategy_logic(strategy).__name__.endswith("breakout")
        assert run(strategy,load_bars(ROOT/"data/demo_ohlcv.csv"))["equity_curve"]
