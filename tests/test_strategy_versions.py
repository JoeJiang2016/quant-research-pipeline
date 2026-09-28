import copy
from pathlib import Path
import pytest
from backtest.strategy import compare, fingerprint, load_strategy, version_directory

CANONICAL=Path("strategies/breakout_001/v1.0.0/strategy.yaml")
SECOND=Path("strategies/breakout_001/v1.1.0/strategy.yaml")

def test_canonical_version_is_semver_and_fingerprint_is_deterministic():
    strategy=load_strategy(CANONICAL)
    assert strategy["strategy_id"] == "breakout_001"
    assert strategy["strategy_version"] == "1.0.0"
    assert fingerprint(strategy) == fingerprint(copy.deepcopy(strategy))

def test_metadata_does_not_change_fingerprint_but_behavior_does():
    strategy=load_strategy(CANONICAL); metadata=copy.deepcopy(strategy); metadata["description"]="different words"
    changed=copy.deepcopy(strategy); changed["exit"]["stop_atr_multiple"]=2.5
    assert fingerprint(metadata) == fingerprint(strategy)
    assert fingerprint(changed) != fingerprint(strategy)

def test_version_directory_mismatch_is_rejected(tmp_path):
    target=tmp_path/"v1.1.0"; target.mkdir(); text=CANONICAL.read_text().replace('"1.0.0"','"1.1.0"')
    (target/"not_strategy.yaml").write_text(text)
    with pytest.raises(ValueError): load_strategy(target/"not_strategy.yaml")

def test_comparison_reports_only_behavior_changes():
    strategy=load_strategy(CANONICAL); updated=copy.deepcopy(strategy); updated["description"]="metadata"; assert compare(strategy,updated) == []
    updated["execution"]["slippage_bps"]=10
    assert compare(strategy,updated) == [{"field":"execution.slippage_bps","left":5,"right":10}]

def test_historical_and_new_versions_are_readable_and_distinct():
    original,updated=load_strategy(CANONICAL),load_strategy(SECOND)
    assert fingerprint(original) != fingerprint(updated)
    assert compare(original,updated) == [{"field":"exit.stop_atr_multiple","left":2.0,"right":2.5}]

def test_duplicate_version_creation_is_refused():
    with pytest.raises(FileExistsError): version_directory(CANONICAL.parents[1],"1.0.0")
