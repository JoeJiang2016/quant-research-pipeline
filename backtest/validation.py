"""Schema validation kept separate from runner side effects."""
import json
from pathlib import Path
from jsonschema import ValidationError, validate as validate_jsonschema

ROOT = Path(__file__).resolve().parents[1]


def validate_strategy(strategy):
    try:
        validate_jsonschema(strategy, json.loads((ROOT / "schemas" / "strategy.schema.json").read_text()))
    except ValidationError as exc:
        raise ValueError("strategy does not conform to schema") from exc
    if strategy["execution"]["fill_time"] != "next_bar_open":
        raise ValueError("non-causal fill_time is prohibited")
    evaluation = strategy.get("evaluation")
    if evaluation and evaluation["in_sample_end"] >= evaluation["out_of_sample_start"]:
        raise ValueError("in_sample_end must precede out_of_sample_start")


def validate_result(result):
    try:
        validate_jsonschema(result, json.loads((ROOT / "schemas" / "backtest_result.schema.json").read_text()))
    except ValidationError as exc:
        raise ValueError("backtest result does not conform to schema") from exc
    for trade in result["trade_log"]:
        if trade["entry_time"] <= trade["signal_time"]:
            raise ValueError("trade log violates next-bar execution")
        if trade["exit_time"] < trade["entry_time"]:
            raise ValueError("trade log exit precedes entry")
