"""Fail-fast mapping from canonical strategy specs to signal logic."""
from backtest.strategies import breakout, pullback

_IMPLEMENTATIONS = {"breakout": breakout, "close_breakout": breakout, "pullback_trend": pullback}


def get_strategy_logic(strategy):
    # Pre-dispatcher in-memory fixtures had only lookback/direction. Canonical
    # specs must identify their type/rule; this fallback preserves those tests.
    strategy_type = strategy.get("strategy_type") or strategy.get("entry", {}).get("rule", "close_breakout")
    try:
        return _IMPLEMENTATIONS[strategy_type]
    except KeyError as exc:
        raise ValueError(f"unknown strategy type: {strategy_type}") from exc
