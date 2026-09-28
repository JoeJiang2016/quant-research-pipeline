import copy
import csv
import json
from pathlib import Path

import pytest

from scripts.run_cross_symbol_validation import EXPECTED_FINGERPRINTS, STRATEGIES
from scripts.run_holdout_validation import (
    CANONICAL_COSTS, COHORT_ID, IS_WINDOW, OOS_WINDOW, SEEN_PILOT, SEED,
    acquisition_config, acquire_cohort, aggregate_holdout,
    deterministic_selection, file_sha256, freeze_experiment_specs, normalized_symbols,
    validate_frozen_cohort,
)

ROOT = Path(__file__).resolve().parents[1]


def _source(path, symbols):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle); writer.writerow(["Symbol"])
        writer.writerows([[symbol] for symbol in symbols])


def test_deterministic_selection_same_seed_and_source_same_30():
    symbols = [f"S{i:03d}" for i in range(50)] + list(SEEN_PILOT)
    first = deterministic_selection(symbols)
    assert first == deterministic_selection(reversed(symbols))
    assert len(first) == 30 and not set(first).intersection(SEEN_PILOT)
    assert SEED == "quant_research_holdout_v1"


def test_normalization_is_deterministic_and_removes_exact_duplicates(tmp_path):
    source = tmp_path / "symbols.csv"
    _source(source, [" aapl ", "AAPL", " msft", "", "brk.b"])
    raw, unique = normalized_symbols(source)
    assert raw == ["AAPL", "AAPL", "MSFT", "BRK.B"]
    assert unique == ["AAPL", "BRK.B", "MSFT"]


def test_committed_cohort_records_frozen_selection_and_checksum():
    cohort = json.loads((ROOT / "research/cohorts/us_equity_holdout_v1.json").read_text())
    assert cohort["cohort_id"] == COHORT_ID
    assert len(cohort["selected_symbols"]) == 30
    assert len(cohort["source_file_sha256"]) == 64
    assert not set(cohort["selected_symbols"]).intersection(SEEN_PILOT)


def test_changed_cohort_manifest_is_rejected_with_offline_source(tmp_path):
    source = tmp_path / "symbols.csv"
    _source(source, [f"S{i:03d}" for i in range(40)] + list(SEEN_PILOT))
    raw, unique = normalized_symbols(source)
    source_checksum = file_sha256(source)
    cohort = {"cohort_id": COHORT_ID, "source_file_sha256": source_checksum,
              "source_symbol_count": len(raw), "duplicate_count": len(raw) - len(unique),
              "selected_symbols": deterministic_selection(unique)}
    cohort["selected_symbols"][0] = "AAPL"
    path = tmp_path / "cohort.json"; path.write_text(json.dumps(cohort))
    with pytest.raises(RuntimeError, match="frozen cohort validation failed"):
        validate_frozen_cohort(path=path, source_path=source,
                               expected_sha256=source_checksum)


def test_acquisition_config_reuses_canonical_contract():
    config = acquisition_config("TEST")
    assert config["library_version"] == "1.7.0"
    assert config["common_parameters"]["actions"] is True
    assert config["common_parameters"]["interval"] == "1d"
    assert config["start"] == "2015-05-26" and config["end_exclusive"] == "2025-10-17"
    assert config["asset_class"] == "equity" and config["country"] == "US"


def test_failed_symbol_is_retained_and_not_replaced(tmp_path):
    cohort = {"selected_symbols": ["FAIL", "OK"]}
    calls = []

    def fake(config, *, yf):
        calls.append(config["symbol"])
        if config["symbol"] == "FAIL":
            raise RuntimeError("offline fixture failure")
        manifest = {"dataset_id": "ok", "dataset_version": "1", "start": "2015-05-26",
                    "end": "2025-10-16", "processed_file_sha256": "a" * 64,
                    "quality_summary": {"canonical_null_count": 0, "malformed_rows": 0,
                    "duplicate_timestamps": 0, "invalid_ohlc": 0, "negative_volume": 0,
                    "nan_or_infinity": 0, "strictly_increasing": True}}
        return {"auto_adjusted": {"manifest": manifest,
                "manifest_path": tmp_path / "ok.json"},
                "acquisition_manifest": {"provider_artifacts": {
                    "raw": {"sha256": "b" * 64}, "auto_adjusted": {"sha256": "c" * 64}},
                    "corporate_actions": {"event_counts": {}}}}

    result = acquire_cohort(cohort, yf=object(), max_attempts=2, acquire_one=fake,
                            status_path=tmp_path / "status.json")
    assert [item["symbol"] for item in result["symbols"]] == ["FAIL", "OK"]
    assert result["symbols"][0]["status"] == "acquisition_failed"
    assert calls == ["FAIL", "FAIL", "OK"]


def test_experiment_specs_have_identical_dates_cost_semantics_and_no_rolling(tmp_path):
    manifest = tmp_path / "dataset.json"; manifest.write_text("{}")
    statuses = [{"symbol": "ABC", "status": "valid", "dataset_id": "abc",
                 "dataset_manifest_path": str(manifest)}]
    paths = freeze_experiment_specs(statuses, tmp_path / "specs")
    spec = __import__("yaml").safe_load(paths["ABC"].read_text())
    assert spec["evaluation"] == {"in_sample": IS_WINDOW, "out_of_sample": OOS_WINDOW}
    assert spec["walk_forward"]["enabled"] is False
    assert spec["cost_sensitivity"]["enabled"] is False
    assert [item["strategy_version"] for item in spec["strategies"]] == ["0.2.0"] * 3


def test_aggregate_retains_zero_trade_and_negative_results_without_mutation():
    records = []
    for strategy_id in STRATEGIES:
        for symbol, value, trades in (("NEG", -.1, 1), ("ZERO", 0.0, 0), ("POS", .2, 2)):
            records.append({"symbol": symbol, "strategy_id": strategy_id,
                            "oos": {"total_return": value, "profit_factor": None if not trades else 1,
                                    "sharpe": value, "max_drawdown": abs(value), "trades": trades}})
    original = copy.deepcopy(records)
    result = aggregate_holdout(records, invalid_count=2)
    assert records == original
    assert all(item["valid_symbol_count"] == 3 and item["invalid_symbol_count"] == 2
               for item in result.values())
    assert all(item["negative_oos_symbols"] == item["zero_return_oos_symbols"] == 1
               for item in result.values())


def test_output_fields_contain_no_selection_labels():
    prohibited = {"rank", "score", "winner", "best", "approved", "rejected", "promotion"}
    sample = aggregate_holdout([
        {"strategy_id": strategy_id, "oos": {"total_return": .1, "profit_factor": 1,
         "sharpe": 1, "max_drawdown": .1, "trades": 1}} for strategy_id in STRATEGIES], 0)
    assert not prohibited.intersection(str(sample).lower().replace("'", " ").split())
    assert set(EXPECTED_FINGERPRINTS) == set(STRATEGIES)
    assert CANONICAL_COSTS == {"commission_per_trade": 1.0, "slippage_bps": 5}
