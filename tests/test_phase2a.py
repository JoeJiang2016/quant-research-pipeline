import csv
from pathlib import Path
import pytest
import copy
from backtest.datasets import create_manifest, load_dataset
from backtest.engine.core import metrics, run
from backtest.walk_forward import build_folds, stitched_oos_equity
from scripts.run_walk_forward import synthetic_demo

def write_csv(path, rows):
    with Path(path).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp","open","high","low","close","volume","symbol"]); w.writeheader(); w.writerows(rows)

def rows():
    return [{"timestamp":"2024-01-01T00:00:00+00:00","open":"10","high":"11","low":"9","close":"10","volume":"1","symbol":"DEMO"}, {"timestamp":"2024-01-02T00:00:00+00:00","open":"10","high":"12","low":"10","close":"11","volume":"2","symbol":"DEMO"}]

def test_csv_load_and_manifest_checksum_is_reproducible(tmp_path):
    source=tmp_path/"demo.csv"; write_csv(source, rows())
    assert len(load_dataset(source, symbol="DEMO", timeframe="1D")) == 2
    assert create_manifest(source, dataset_id="demo", symbol="DEMO", timeframe="1D", timezone="UTC", source="synthetic")["sha256"] == create_manifest(source, dataset_id="demo", symbol="DEMO", timeframe="1D", timezone="UTC", source="synthetic")["sha256"]

@pytest.mark.parametrize("key,value", [("timestamp","2024-01-01T00:00:00"),("high","8"),("close","nan")])
def test_bad_dataset_fails_fast(tmp_path,key,value):
    source=tmp_path/"bad.csv"; data=rows(); data[1][key]=value; write_csv(source,data)
    with pytest.raises(ValueError): load_dataset(source, symbol="DEMO", timeframe="1D")

def test_duplicate_timestamp_rejected(tmp_path):
    source=tmp_path/"duplicate.csv"; data=rows(); data[1]["timestamp"]=data[0]["timestamp"]; write_csv(source,data)
    with pytest.raises(ValueError): load_dataset(source, symbol="DEMO", timeframe="1D")

def test_rolling_and_expanding_boundaries_do_not_leak():
    rolling=build_folds(12,train_bars=4,test_bars=2,step=2); expanding=build_folds(12,train_bars=4,test_bars=2,step=2,anchored=True)
    assert [(f.train_start,f.train_end,f.test_start,f.test_end) for f in rolling] == [(0,4,4,6),(2,6,6,8),(4,8,8,10),(6,10,10,12)]
    assert all(f.train_start == 0 and f.train_end <= f.test_start for f in expanding)

def test_stitched_curve_is_oos_only_and_ordered():
    assert stitched_oos_equity([[{"timestamp":"2","equity":1}], [{"timestamp":"3","equity":2}]])[0]["timestamp"] == "2"
    with pytest.raises(ValueError): stitched_oos_equity([[{"timestamp":"2","equity":1}], [{"timestamp":"2","equity":2}]])

def test_synthetic_demo_has_deterministic_oos_trade_and_no_is_output(tmp_path):
    path=tmp_path/"demo_test_data.csv"; synthetic_demo(path); first=path.read_bytes(); synthetic_demo(path); assert path.read_bytes() == first
    bars=load_dataset(path,symbol="DEMO",timeframe="1d"); folds=build_folds(len(bars),train_bars=28,test_bars=24)
    oos_results=[run(__import__("yaml").safe_load(Path("strategies/breakout_001/v1.0.0/strategy.yaml").read_text()),bars[f.test_start:f.test_end]) for f in folds]
    trades=[trade for result in oos_results for trade in result["trades"]]
    assert trades and all(bars[folds[0].test_start]["timestamp"] <= trade["entry_time"] for trade in trades)
    assert [f.fold_id for f in folds] == ["fold_001","fold_002"]
    stitched=stitched_oos_equity([result["equity_curve"] for result in oos_results])
    assert {point["timestamp"] for point in stitched}.issubset({bar["timestamp"] for f in folds for bar in bars[f.test_start:f.test_end]})

def test_higher_costs_do_not_improve_deterministic_net_result(tmp_path):
    path=tmp_path/"demo_test_data.csv"; synthetic_demo(path); bars=load_dataset(path,symbol="DEMO",timeframe="1d"); strategy=__import__("yaml").safe_load(Path("strategies/breakout_001/v1.0.0/strategy.yaml").read_text()); oos=bars[28:52]
    base=metrics(run(strategy,oos),strategy["risk"]["initial_equity"])["total_return"]
    higher_commission=copy.deepcopy(strategy); higher_commission["execution"]["commission_per_trade"]*=2
    higher_slippage=copy.deepcopy(strategy); higher_slippage["execution"]["slippage_bps"]*=2
    assert metrics(run(higher_commission,oos),higher_commission["risk"]["initial_equity"])["total_return"] <= base
    assert metrics(run(higher_slippage,oos),higher_slippage["risk"]["initial_equity"])["total_return"] <= base
