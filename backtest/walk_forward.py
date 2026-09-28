"""Fixed-parameter, deterministic walk-forward boundaries and OOS-only aggregation."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Fold:
    fold_id: str
    train_start: int
    train_end: int
    test_start: int
    test_end: int


def build_folds(total_bars, *, train_bars, test_bars, step=None, anchored=False):
    if min(total_bars, train_bars, test_bars) <= 0:
        raise ValueError("bar counts must be positive")
    step = step or test_bars
    if step <= 0:
        raise ValueError("step must be positive")
    folds, test_start = [], train_bars
    while test_start + test_bars <= total_bars:
        train_start = 0 if anchored else test_start - train_bars
        fold = Fold(f"fold_{len(folds) + 1:03d}", train_start, test_start, test_start, test_start + test_bars)
        if fold.train_end > fold.test_start:
            raise AssertionError("future data entered training")
        folds.append(fold)
        test_start += step
    if not folds:
        raise ValueError("not enough bars for one train/OOS fold")
    return folds


def stitched_oos_equity(fold_curves):
    """Curves must already be restricted to OOS rows; chronological duplicates fail."""
    stitched, seen, previous = [], set(), None
    for curve in fold_curves:
        for point in curve:
            stamp = point["timestamp"]
            if stamp in seen or (previous is not None and stamp <= previous):
                raise ValueError("OOS curves overlap or are not strictly ordered")
            stitched.append(point); seen.add(stamp); previous = stamp
    return stitched
