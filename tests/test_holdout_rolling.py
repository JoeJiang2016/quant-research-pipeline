import copy
import inspect

import pytest

import scripts.run_holdout_rolling as module
from backtest.walk_forward import build_folds
from scripts.run_cross_symbol_validation import EXPECTED_FINGERPRINTS, STRATEGIES
from scripts.run_holdout_rolling import (
    EXPECTED_DATASETS, INSUFFICIENT_SYMBOLS, REVEAL_STATUS,
    aggregate_cells, chronological_breadth, positive_fold_distribution,
    summarize_symbol_folds,
)
from scripts.run_holdout_validation import SEEN_PILOT


def _records(symbol_count=28):
    records = []
    for strategy_index, strategy_id in enumerate(STRATEGIES):
        for fold_number in range(1, 8):
            for symbol_number in range(symbol_count):
                value = (symbol_number - 13 + fold_number + strategy_index) / 1000
                records.append({"symbol": f"S{symbol_number:02d}", "strategy_id": strategy_id,
                    "fold_id": f"fold_{fold_number:03d}",
                    "test_start": f"202{fold_number}-01-01", "test_end": f"202{fold_number}-12-31",
                    "metrics": {"total_return": value, "profit_factor": 1 + value,
                                "sharpe": value * 10, "max_drawdown": abs(value),
                                "trades": 0 if symbol_number == 0 else 1}})
    return records


def test_exact_holdout_membership_and_dataset_freeze_constants():
    assert len(EXPECTED_DATASETS) == 28
    assert set(EXPECTED_DATASETS).isdisjoint(SEEN_PILOT)
    assert set(INSUFFICIENT_SYMBOLS) == {"CTVA", "SOLV"}
    assert set(EXPECTED_DATASETS).isdisjoint(INSUFFICIENT_SYMBOLS)
    assert all(len(checksum) == 64 for _, checksum in EXPECTED_DATASETS.values())


def test_revealed_status_and_strategy_fingerprints_are_explicit():
    assert REVEAL_STATUS == "revealed_holdout_after_3d3"
    assert set(EXPECTED_FINGERPRINTS) == set(STRATEGIES)
    assert all(len(value) == 64 for value in EXPECTED_FINGERPRINTS.values())


def test_identical_complete_fold_configuration_is_exactly_seven():
    folds = build_folds(2616, train_bars=756, test_bars=252, step=252, anchored=False)
    assert len(folds) == 7
    assert all(left.test_end == right.test_start for left, right in zip(folds, folds[1:]))
    assert folds[-1].test_end == 2520 and 2616 - folds[-1].test_end == 96


def test_per_symbol_summary_retains_negative_and_zero_trade_folds():
    records = [item for item in _records(28)
               if item["strategy_id"] == STRATEGIES[0] and item["symbol"] == "S00"]
    result = summarize_symbol_folds(records)
    assert result["fold_count"] == 7
    assert result["negative_return_folds"] > 0
    assert result["total_trades"] == 0


def test_positive_fold_distribution_is_deterministic():
    summaries = {}
    for symbol_number in range(28):
        summaries[f"S{symbol_number:02d}"] = {
            strategy_id: {"positive_return_folds": (symbol_number + index) % 8}
            for index, strategy_id in enumerate(STRATEGIES)}
    first = positive_fold_distribution(summaries)
    assert first == positive_fold_distribution(dict(reversed(list(summaries.items()))))
    assert all(sum(values.values()) == 28 for values in first.values())


def test_cell_aggregation_is_deterministic_and_retains_all_cells():
    records = _records()
    original = copy.deepcopy(records)
    first = aggregate_cells(records)
    assert first == aggregate_cells(list(reversed(records)))
    assert records == original
    assert all(value["cell_count"] == 196 for value in first.values())
    assert all(value["positive_cells"] + value["negative_cells"] + value["zero_cells"] == 196
               for value in first.values())


def test_chronological_breadth_is_deterministic_and_complete():
    records = _records()
    first = chronological_breadth(records)
    assert first == chronological_breadth(list(reversed(records)))
    assert all(len(rows) == 7 for rows in first.values())
    assert all(row["positive_symbols"] + row["negative_symbols"] + row["zero_symbols"] == 28
               for rows in first.values() for row in rows)


def test_breadth_fails_closed_on_missing_symbol_cell():
    with pytest.raises(RuntimeError, match="incomplete or misaligned"):
        chronological_breadth(_records()[:-1])


def test_runner_has_no_network_or_optimization_path():
    source = inspect.getsource(module.run_holdout_rolling).lower()
    assert "yfinance" not in source and "download" not in source
    assert "optimizer" not in source and '"parameter_selection": "none"' in source
    assert '"boundary_mode": "flat_start"' in source


def test_factual_output_keys_have_no_selection_labels():
    prohibited = {"rank", "score", "winner", "best", "approved", "rejected", "promotion"}
    output = {"aggregate": aggregate_cells(_records()),
              "breadth": chronological_breadth(_records())}

    def keys(value):
        if isinstance(value, dict):
            return set(value).union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value), set())
        return set()

    assert not prohibited.intersection(keys(output))
