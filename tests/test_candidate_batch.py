import json, shutil
from pathlib import Path
import pytest
from backtest.candidates import ALLOWED_FIELDS, load_registry
from scripts.run_candidate_batch import run_batch

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"strategies/candidates.json"

def test_registry_loads_three_metadata_only_candidates():
    candidates=load_registry(REGISTRY)
    assert [item["strategy_id"] for item in candidates] == ["breakout_trend_001","pullback_trend_001","mean_reversion_001"]
    raw=json.loads(REGISTRY.read_text())
    assert all(set(item)==ALLOWED_FIELDS for item in raw)

def test_duplicate_and_nonexistent_registry_entries_fail(tmp_path):
    original=json.loads(REGISTRY.read_text())
    duplicate=tmp_path/"duplicate.json"; duplicate.write_text(json.dumps(original+[original[0]]))
    with pytest.raises(ValueError,match="duplicate"): load_registry(duplicate)
    missing=tmp_path/"missing.json"; missing.write_text(json.dumps([{"strategy_id":"missing","version":"0.1.0","family":"x","status":"candidate"}]))
    with pytest.raises(ValueError,match="nonexistent"): load_registry(missing)

def test_registry_yaml_identity_mismatch_fails(tmp_path):
    strategies=tmp_path/"strategies"; target=strategies/"wrong_id/v0.1.0"; target.mkdir(parents=True)
    shutil.copy(ROOT/"strategies/breakout_trend_001/v0.1.0/strategy.yaml",target/"strategy.yaml")
    registry=tmp_path/"registry.json"; registry.write_text(json.dumps([{"strategy_id":"wrong_id","version":"0.1.0","family":"x","status":"candidate"}]))
    with pytest.raises(ValueError,match="identity"): load_registry(registry,strategies)

def test_batch_outputs_three_provenanced_results_without_ranking(tmp_path):
    target=run_batch(REGISTRY,tmp_path); manifest=json.loads((target/"manifest.json").read_text()); summary=json.loads((target/"candidate_summary.json").read_text())
    assert manifest["candidate_count"] == 3 and len(manifest["candidates"]) == 3
    assert len(summary["candidates"]) == 3 and summary["comparable_performance"] is False
    prohibited={"rank","winner","score","approved","rejected","best"}
    assert not prohibited.intersection(json.dumps(summary).lower().replace('"',' ').replace(':',' ').replace(',',' ').split())
    for identity in manifest["candidates"]:
        result=json.loads((target/identity["strategy_id"]/"backtest_result.json").read_text())
        assert result["strategy_fingerprint"] == identity["fingerprint"]

def test_generic_exit_hook_has_no_mean_reversion_hardcoding():
    source=(ROOT/"backtest/engine/core.py").read_text()
    assert "evaluate_exit" in source
    assert "mean_reversion" not in source and "zscore" not in source
