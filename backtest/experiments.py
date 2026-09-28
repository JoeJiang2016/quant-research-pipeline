"""Canonical research experiment validation and identity."""
import hashlib, json
from pathlib import Path
import yaml
from jsonschema import ValidationError, validate

ROOT=Path(__file__).resolve().parents[1]
FINGERPRINT_FIELDS=("experiment_id","experiment_version","dataset","strategies","research_window","evaluation","walk_forward","cost_sensitivity")

def experiment_fingerprint(experiment):
    projection={key:experiment[key] for key in FINGERPRINT_FIELDS}
    return hashlib.sha256(json.dumps(projection,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def load_experiment(path):
    experiment=yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    try: validate(experiment,json.loads((ROOT/"schemas/research_experiment.schema.json").read_text()))
    except ValidationError as exc: raise ValueError("research experiment does not conform to schema") from exc
    windows=[experiment["research_window"],experiment["evaluation"]["in_sample"],experiment["evaluation"]["out_of_sample"]]
    if any(window["start"] > window["end"] for window in windows): raise ValueError("experiment window start must not exceed end")
    return experiment

def comparable_performance(records):
    """Comparable only when dataset, window, timeframe, and cost scenario match."""
    keys=("dataset_checksum","research_window","timeframe","cost_scenario")
    return bool(records) and all(all(record[key] == records[0][key] for key in keys) for record in records[1:])
