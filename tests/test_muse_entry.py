import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY_PATH = ROOT / "integration" / "muse_entry.json"


def test_muse_canonical_entry_is_valid_and_references_existing_paths():
    entry = json.loads(ENTRY_PATH.read_text(encoding="utf-8"))

    assert entry["entry_version"]
    assert entry["schema_version"]
    assert entry["allowed_status"] == ["candidate"]
    assert entry["required_output_format"]["format"] == "YAML"
    assert entry["required_output_format"]["required_status"] == "candidate"

    schema = ROOT / entry["strategy_schema_path"]
    example = ROOT / entry["candidate_example_path"]
    output_directory = ROOT / entry["candidate_output_directory"]
    assert schema.is_file()
    assert example.is_file()
    assert output_directory.is_dir()
    assert output_directory == example.parent

    strategy_schema = json.loads(schema.read_text(encoding="utf-8"))
    assert strategy_schema["properties"]["status"]["const"] == "candidate"
    assert "status" in strategy_schema["required"]
