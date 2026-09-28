import copy, csv, json
from pathlib import Path
import pytest, yaml
from backtest.datasets import import_dataset
from backtest.experiments import comparable_performance, experiment_fingerprint, load_experiment
from backtest.strategy import fingerprint, load_strategy
from scripts.run_research_experiment import run_experiment

ROOT=Path(__file__).resolve().parents[1]
SAMPLE=ROOT/"research/experiments/batch1_baseline.yaml"

def source(path, rows=None, headers=None):
    headers=headers or ["Date","Open","High","Low","Close","Volume"]
    rows=rows or [["2024-01-01",10,11,9,10,1],["2024-01-02",10,12,10,11,2]]
    with path.open("w",newline="") as handle: writer=csv.writer(handle,lineterminator="\n"); writer.writerow(headers); writer.writerows(rows)
    return path

def imported(tmp_path, **overrides):
    mapping={"timestamp":"Date","open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"}
    options=dict(dataset_id="fixture",version="1",symbol="DEMO",timeframe="1d",source_timezone="UTC",source="test",column_mapping=mapping,output_root=tmp_path/"data")
    options.update(overrides); return import_dataset(source(tmp_path/"input.csv"),**options)

def test_experiment_schema_and_fingerprint_independence():
    experiment=load_experiment(SAMPLE); assert experiment_fingerprint(experiment)==experiment_fingerprint(copy.deepcopy(experiment))
    strategy=load_strategy(ROOT/"strategies/breakout_trend_001/v0.1.0/strategy.yaml"); before=fingerprint(strategy)
    changed=copy.deepcopy(experiment); changed["dataset"]["dataset_id"]="other"; assert experiment_fingerprint(changed)!=experiment_fingerprint(experiment)
    changed=copy.deepcopy(experiment); changed["evaluation"]["out_of_sample"]["start"]="2023-01-22T00:00:00Z"; assert experiment_fingerprint(changed)!=experiment_fingerprint(experiment)
    assert fingerprint(strategy)==before

def test_canonical_import_mapping_timezone_checksums_and_raw_immutability(tmp_path):
    input_path=source(tmp_path/"input.csv"); original=input_path.read_bytes(); mapping={"timestamp":"Date","open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"}
    result=import_dataset(input_path,dataset_id="fixture",version="1",symbol="DEMO",timeframe="1d",source_timezone="UTC",source="test",column_mapping=mapping,output_root=tmp_path/"data")
    assert input_path.read_bytes()==original and result["raw_path"].read_bytes()==original
    processed=result["processed_path"].read_text(); assert "2024-01-01T00:00:00Z" in processed
    manifest=result["manifest"]; assert manifest["raw_file_sha256"] and manifest["processed_file_sha256"] and manifest["column_mapping"]==mapping
    again=import_dataset(input_path,dataset_id="fixture",version="1",symbol="DEMO",timeframe="1d",source_timezone="UTC",source="test",column_mapping=mapping,output_root=tmp_path/"data")
    assert again["manifest"]["processed_file_sha256"]==manifest["processed_file_sha256"]

def test_naive_timestamp_requires_timezone(tmp_path):
    with pytest.raises(ValueError,match="timezone"): imported(tmp_path,source_timezone=None)

@pytest.mark.parametrize("rows",[[["2024-01-01",10,11,9,10,1],["2024-01-01",10,11,9,10,1]],[["2024-01-01",10,9,8,10,1]],[["2024-01-01",10,11,9,"nan",1]]])
def test_import_rejects_duplicate_invalid_ohlc_and_nan(tmp_path,rows):
    path=source(tmp_path/"input.csv",rows=rows); mapping={"timestamp":"Date","open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"}
    with pytest.raises(ValueError): import_dataset(path,dataset_id="bad",symbol="DEMO",timeframe="1d",source_timezone="UTC",source="test",column_mapping=mapping,output_root=tmp_path/"data")

def make_experiment(tmp_path, manifest, *, symbol="DEMO", timeframe="1d"):
    experiment=yaml.safe_load(SAMPLE.read_text()); experiment["dataset"]={"dataset_id":manifest["dataset_id"],"manifest_path":str(tmp_path/"data/manifests/fixture_v1.json")}; path=tmp_path/"experiment.yaml"; path.write_text(yaml.safe_dump(experiment)); return path

def shared_import(tmp_path, symbol="DEMO", timeframe="1d"):
    mapping={name:name for name in ("timestamp","open","high","low","close","volume")}
    return import_dataset(ROOT/"data/demo_ohlcv.csv",dataset_id="fixture",version="1",symbol=symbol,timeframe=timeframe,source_timezone="UTC",source="test",column_mapping=mapping,output_root=tmp_path/"data")

def test_experiment_runner_shared_dataset_and_compatibility(tmp_path):
    fixture=shared_import(tmp_path); experiment=make_experiment(tmp_path,fixture["manifest"]); target=run_experiment(experiment,tmp_path/"reports")
    manifest=json.loads((target/"experiment_manifest.json").read_text()); assert len(manifest["strategies"])==3 and manifest["comparable_performance"] is True
    bad=copy.deepcopy(fixture["manifest"]); bad["timeframe"]="1h"; fixture["manifest_path"].write_text(json.dumps(bad))
    with pytest.raises(ValueError,match="timeframe"): run_experiment(experiment,tmp_path/"bad-reports")

def test_universe_mismatch_and_checksum_comparability(tmp_path):
    fixture=shared_import(tmp_path,symbol="OTHER"); experiment=make_experiment(tmp_path,fixture["manifest"])
    with pytest.raises(ValueError,match="universe"): run_experiment(experiment,tmp_path/"reports")
    base={"dataset_checksum":"a","research_window":{"start":"1","end":"2"},"timeframe":"1d","cost_scenario":{"name":"base"}}
    assert comparable_performance([base,copy.deepcopy(base)]) is True
    changed=copy.deepcopy(base); changed["dataset_checksum"]="b"; assert comparable_performance([base,changed]) is False
