from backtest.engine.core import run

BASE={"entry":{"lookback_bars":2,"direction":"long"},"exit":{"atr_period":2,"stop_atr_multiple":2,"take_profit_atr_multiple":4},"risk":{"initial_equity":10000,"risk_per_trade_pct":.01},"execution":{"commission_per_trade":1,"slippage_bps":0}}
def bars():
    return [{"timestamp":str(i),"open":100,"high":101,"low":99,"close":100} for i in range(3)]+[{"timestamp":"3","open":101,"high":102,"low":100,"close":102},{"timestamp":"4","open":102,"high":110,"low":101,"close":109},{"timestamp":"5","open":109,"high":112,"low":108,"close":109}]
def test_next_bar_execution_and_single_order():
    result=run(BASE,bars())
    assert len(result["trades"]) == 1
    assert result["trades"][0]["signal_time"] == "3"
    assert result["trades"][0]["entry_time"] == "4"
def test_stop_precedes_target_when_same_bar():
    s={**BASE, "exit": {"atr_period":2,"stop_atr_multiple":.1,"take_profit_atr_multiple":.1}}
    result=run(s,bars())
    assert result["trades"][0]["exit_reason"] == "stop"
def test_commission_and_slippage_are_recorded():
    s={**BASE, "execution": {"commission_per_trade":2,"slippage_bps":10}}
    result=run(s,bars())
    assert result["commission"] == 4
    assert result["slippage"] > 0
