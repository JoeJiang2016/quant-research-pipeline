import copy
import inspect

import pytest

from backtest.walk_forward import build_folds
from scripts.run_cross_symbol_rolling import (
    EXPECTED_DATASET_CHECKSUMS, EXPECTED_FINGERPRINTS, FOLD_CONFIG,
    aggregate_cells, fold_breadth, percentile, stitch_symbol_curves,
    verify_aapl_folds,
)
import scripts.run_cross_symbol_rolling as rolling_module
from scripts.run_cross_symbol_validation import COHORT, STRATEGIES


def _records():
    records = []
    for strategy_index, strategy_id in enumerate(STRATEGIES):
        for fold_number in range(1, 8):
            for symbol_index, symbol in enumerate(COHORT):
                value = (symbol_index - 2 + fold_number + strategy_index) / 100
                records.append({
                    "symbol": symbol, "strategy_id": strategy_id,
                    "fold_id": f"fold_{fold_number:03d}",
                    "test_start": f"202{fold_number}-01-01",
                    "test_end": f"202{fold_number}-12-31",
                    "metrics": {"total_return": value, "profit_factor": 1 + value,
                                "max_drawdown": abs(value) / 2, "sharpe": value * 2,
                                "trades": symbol_index + 1},
                })
    return records


def test_frozen_inputs_are_exact_and_complete():
    assert tuple(EXPECTED_DATASET_CHECKSUMS) == COHORT
    assert tuple(EXPECTED_FINGERPRINTS) == STRATEGIES
    assert all(len(value) == 64 for value in EXPECTED_DATASET_CHECKSUMS.values())
    assert all(len(value) == 64 for value in EXPECTED_FINGERPRINTS.values())


def test_fold_boundaries_are_seven_complete_nonoverlapping_windows():
    folds = build_folds(2616, train_bars=FOLD_CONFIG["train_bars"],
                        test_bars=FOLD_CONFIG["test_bars"],
                        step=FOLD_CONFIG["step_bars"], anchored=False)
    assert len(folds) == 7
    assert all(fold.train_end == fold.test_start for fold in folds)
    assert all(folds[i].test_end == folds[i + 1].test_start for i in range(6))
    assert folds[-1].test_end == 2520
    assert 2616 - folds[-1].test_end == 96


def test_all_symbols_share_one_fixed_rolling_configuration():
    assert FOLD_CONFIG == {"train_bars": 756, "test_bars": 252,
                           "step_bars": 252, "anchored": False,
                           "incomplete_final_fold": "excluded"}


def test_percentile_is_deterministic_linear_interpolation():
    assert percentile([4, 1, 3, 2], 0.25) == 1.75
    assert percentile([4, 1, 3, 2], 0.75) == 3.25
    assert percentile([9], 0.25) == 9


def test_cross_cell_aggregation_retains_all_35_cells_per_strategy():
    result = aggregate_cells(_records())
    assert all(item["cell_count"] == 35 for item in result.values())
    assert all(item["positive_return_cells"] + item["negative_return_cells"] +
               item["zero_return_cells"] == 35 for item in result.values())
    assert result == aggregate_cells(list(reversed(_records())))
    assert result[STRATEGIES[0]]["negative_return_cells"] > 0
    assert result[STRATEGIES[0]]["zero_return_cells"] > 0


def test_aggregation_does_not_mutate_parameters_or_records():
    records = _records()
    original = copy.deepcopy(records)
    aggregate_cells(records)
    fold_breadth(records)
    assert records == original


def test_fold_breadth_is_complete_aligned_and_deterministic():
    result = fold_breadth(_records())
    assert all(len(rows) == 7 for rows in result.values())
    assert all(row["positive_symbols"] + row["negative_symbols"] + row["zero_symbols"] == 5
               for rows in result.values() for row in rows)
    assert result == fold_breadth(list(reversed(_records())))


def test_fold_breadth_rejects_missing_or_misaligned_symbol_cells():
    records = _records()
    with pytest.raises(ValueError, match="incomplete or misaligned"):
        fold_breadth(records[:-1])
    altered = copy.deepcopy(records)
    altered[0]["test_end"] = "2099-12-31"
    with pytest.raises(ValueError, match="incomplete or misaligned"):
        fold_breadth(altered)


def test_stitched_equity_is_restricted_to_one_symbol():
    curves = [{"symbol": "AAPL", "curve": [{"timestamp": "2023-01-03", "equity": 1}]},
              {"symbol": "AAPL", "curve": [{"timestamp": "2024-01-03", "equity": 2}]}]
    assert stitch_symbol_curves(curves)["symbol"] == "AAPL"
    curves[1]["symbol"] = "MSFT"
    with pytest.raises(ValueError, match="cannot combine symbols"):
        stitch_symbol_curves(curves)


def test_aapl_reproduction_comparator_checks_boundaries_and_metrics(tmp_path):
    current = {}
    for strategy_id in STRATEGIES:
        row = {"fold_id": "fold_001", "train_start": "a", "train_end": "b",
               "test_start": "c", "test_end": "d",
               "metrics": {"trades": 1, "total_return": 0.1, "profit_factor": 2,
                           "max_drawdown": 0.01, "sharpe": 1, "expectancy": 4,
                           "commission": 2, "slippage": 3}}
        current[strategy_id] = [row]
        path = tmp_path / strategy_id
        path.mkdir()
        (path / "folds.json").write_text(__import__("json").dumps([row]))
    assert verify_aapl_folds(current, tmp_path)
    current[STRATEGIES[0]][0]["metrics"]["trades"] = 2
    with pytest.raises(RuntimeError, match="AAPL fold metric differs"):
        verify_aapl_folds(current, tmp_path)


def test_runner_has_no_optimization_or_parameter_selection_path():
    source = inspect.getsource(rolling_module.run_cross_symbol_rolling)
    assert "optimizer" not in source.lower()
    assert '"parameter_selection": "none"' in source
    assert '"boundary_mode": "flat_start_each_fold"' in source


def test_factual_outputs_have_no_selection_language():
    prohibited = {"rank", "score", "winner", "best", "promotion", "approval", "rejection"}
    output = {"aggregate": aggregate_cells(_records()), "breadth": fold_breadth(_records())}

    def keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()), set())
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value), set())
        return set()

    assert not (keys(output) & prohibited)
