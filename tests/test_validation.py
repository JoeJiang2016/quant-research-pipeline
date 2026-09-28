import pytest
from scripts.run_backtest import validate
from scripts.run_backtest import load_bars
def test_invalid_risk_rejected():
    s={"strategy_id":"a","strategy_version":"1","dataset_id":"d","universe":["X"],"timeframe":"1d","execution":{"fill_time":"next_bar_open"},"entry":{"lookback_bars":2},"exit":{"atr_period":2},"risk":{"risk_per_trade_pct":2}}
    with pytest.raises(ValueError): validate(s)
def test_missing_ohlcv_column_rejected(tmp_path):
    p=tmp_path / "bad.csv"
    p.write_text("timestamp,open,high,low,close\\n2020,1,1,1,1\\n")
    with pytest.raises(ValueError): load_bars(p)
def test_lookahead_fill_rejected():
    s={"strategy_id":"a","strategy_version":"1","dataset_id":"d","universe":["X"],"timeframe":"1d","execution":{"fill_time":"bar_close"},"entry":{"lookback_bars":2},"exit":{"atr_period":2},"risk":{"risk_per_trade_pct":.1}}
    with pytest.raises(ValueError): validate(s)
