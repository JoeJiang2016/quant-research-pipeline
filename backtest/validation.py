"""Schema validation kept separate from runner side effects."""
import json
from pathlib import Path
from jsonschema import ValidationError, validate as validate_jsonschema

ROOT = Path(__file__).resolve().parents[1]


def validate_strategy(strategy):
    # Canonical versioning fields are enforced by backtest.strategy; retain
    # compatibility for legacy candidate files during their explicit migration.
    canonical = {"strategy_type", "pyramiding", "position_sizing", "session", "description", "notes", "author", "created_at"}
    legacy_view = {key: value for key, value in strategy.items() if key not in canonical}
    try:
        validate_jsonschema(legacy_view, json.loads((ROOT / "schemas" / "strategy.schema.json").read_text()))
    except ValidationError as exc:
        raise ValueError("strategy does not conform to schema") from exc
    if strategy["execution"]["fill_time"] != "next_bar_open":
        raise ValueError("non-causal fill_time is prohibited")
    evaluation = strategy.get("evaluation")
    if evaluation and evaluation["in_sample_end"] >= evaluation["out_of_sample_start"]:
        raise ValueError("in_sample_end must precede out_of_sample_start")


def validate_result(result):
    try:
        schema = json.loads((ROOT / "schemas" / "backtest_result.schema.json").read_text())
        schema["required"].append("strategy_fingerprint")
        schema["properties"]["strategy_fingerprint"] = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
        validate_jsonschema(result, schema)
    except ValidationError as exc:
        raise ValueError("backtest result does not conform to schema") from exc
    for trade in result["trade_log"]:
        if trade["entry_time"] <= trade["signal_time"]:
            raise ValueError("trade log violates next-bar execution")
        if trade["exit_time"] < trade["entry_time"]:
            raise ValueError("trade log exit precedes entry")
