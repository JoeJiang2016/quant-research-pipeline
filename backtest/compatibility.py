"""Central strategy-to-dataset eligibility checks with explainable results."""


def strategy_dataset_compatibility(strategy, dataset_manifest):
    reasons = []
    checks = {}
    universe = strategy.get("universe")
    if isinstance(universe, list):
        symbol = dataset_manifest.get("symbol")
        passed = symbol in universe
        checks["symbol"] = {"compatible": passed, "strategy_symbols": universe,
                            "dataset_symbol": symbol}
        if not passed:
            reasons.append(f"dataset symbol {symbol!r} is outside exact-symbol universe")
    elif isinstance(universe, dict) and universe.get("mode") == "asset_class":
        for field in ("asset_class", "country"):
            expected = universe.get(field)
            actual = dataset_manifest.get(field)
            passed = actual == expected
            checks[field] = {"compatible": passed, "expected": expected,
                             "actual": actual}
            if not passed:
                reasons.append(f"dataset {field} {actual!r} does not match {expected!r}")
    else:
        checks["universe"] = {"compatible": False, "actual": universe}
        reasons.append("strategy universe uses an unsupported form")

    expected_timeframe = strategy.get("timeframe")
    actual_timeframe = dataset_manifest.get("timeframe")
    timeframe_ok = actual_timeframe == expected_timeframe
    checks["timeframe"] = {"compatible": timeframe_ok,
                           "expected": expected_timeframe,
                           "actual": actual_timeframe}
    if not timeframe_ok:
        reasons.append(f"dataset timeframe {actual_timeframe!r} does not match {expected_timeframe!r}")
    return {"compatible": not reasons, "reasons": reasons, "checks": checks}
