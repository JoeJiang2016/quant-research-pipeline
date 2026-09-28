import copy
import json
from pathlib import Path

import pytest

from backtest.candidates import load_registry
from backtest.compatibility import strategy_dataset_compatibility
from backtest.strategy import compare, fingerprint, load_strategy
from backtest.validation import validate_strategy

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ("breakout_trend_001", "pullback_trend_001", "mean_reversion_001")


def strategy(family, version):
    return load_strategy(ROOT / "strategies" / family / f"v{version}" / "strategy.yaml")


def aapl_manifest(**changes):
    manifest = {"dataset_id": "aapl_1d_yf_adjusted", "dataset_version": "2",
                "symbol": "AAPL", "asset_class": "equity", "country": "US",
                "timeframe": "1d"}
    manifest.update(changes)
    return manifest


def test_legacy_exact_symbol_universe_remains_supported_and_explainable():
    original = strategy("breakout_trend_001", "0.1.0")
    assert original["universe"] == ["DEMO"]
    assert strategy_dataset_compatibility(original, {
        "symbol": "DEMO", "timeframe": "1d"})["compatible"] is True
    mismatch = strategy_dataset_compatibility(original, aapl_manifest())
    assert mismatch["compatible"] is False
    assert "exact-symbol universe" in mismatch["reasons"][0]


def test_asset_class_universe_schema_validates_without_wildcards():
    current = strategy("breakout_trend_001", "0.2.0")
    validate_strategy(current)
    invalid = copy.deepcopy(current)
    invalid["universe"] = {"mode": "asset_class", "asset_class": "*", "country": "US"}
    with pytest.raises(ValueError, match="schema"):
        validate_strategy(invalid)


@pytest.mark.parametrize("changes,reason", [
    ({"asset_class": "future"}, "asset_class"),
    ({"country": "CA"}, "country"),
    ({"timeframe": "1h"}, "timeframe"),
])
def test_asset_class_country_and_timeframe_mismatches_fail(changes, reason):
    result = strategy_dataset_compatibility(
        strategy("breakout_trend_001", "0.2.0"), aapl_manifest(**changes))
    assert result["compatible"] is False
    assert reason in " ".join(result["reasons"])


def test_aapl_v2_compatibility_for_all_versions():
    for family in FAMILIES:
        assert strategy_dataset_compatibility(
            strategy(family, "0.1.0"), aapl_manifest())["compatible"] is False
        result = strategy_dataset_compatibility(strategy(family, "0.2.0"), aapl_manifest())
        assert result["compatible"] is True
        assert result["reasons"] == []


def test_new_versions_change_only_universe_behavior_and_fingerprint():
    unchanged = ("entry", "exit", "risk", "execution", "position_sizing",
                 "pyramiding", "timeframe", "session")
    for family in FAMILIES:
        old, new = strategy(family, "0.1.0"), strategy(family, "0.2.0")
        assert fingerprint(old) != fingerprint(new)
        assert compare(old, new) == [{"field": "universe", "left": ["DEMO"],
                                     "right": {"mode": "asset_class",
                                               "asset_class": "equity",
                                               "country": "US"}}]
        assert all(old[field] == new[field] for field in unchanged)


def test_registry_resolves_one_current_version_per_family():
    resolved = load_registry()
    assert len(resolved) == len(FAMILIES)
    assert {item["strategy_id"] for item in resolved} == set(FAMILIES)
    assert {item["version"] for item in resolved} == {"0.2.0"}
