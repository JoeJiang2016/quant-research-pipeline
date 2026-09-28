import hashlib
import json
from pathlib import Path

from backtest.strategy import fingerprint, load_strategy
from scripts.run_cross_symbol_validation import EXPECTED_FINGERPRINTS, STRATEGIES

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "decisions/evidence/baseline_strategy_cycle_v1"
MANIFEST = json.loads((PACKET / "evidence_manifest.json").read_text(encoding="utf-8"))


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_evidence_packet_has_six_existing_artifact_references():
    phases = MANIFEST["research_phases"]
    assert [item["phase"] for item in phases] == ["3C-2", "3C-3", "3D-1", "3D-2", "3D-3", "3D-4"]
    assert all(item["artifacts"] for item in phases)
    for phase in phases:
        for artifact in phase["artifacts"]:
            assert artifact["path"].startswith("reports/")
            assert len(artifact["sha256"]) == 64
            path = ROOT / artifact["path"]
            # Generated reports are intentionally gitignored, but local evidence must match.
            if path.exists():
                assert _sha256(path) == artifact["sha256"]


def test_packet_did_not_execute_new_evaluation_and_has_no_executable_files():
    assert MANIFEST["generation_mode"] == "existing_artifact_read_only"
    assert MANIFEST["new_evaluation_executed"] is False
    assert not list(PACKET.glob("*.py"))


def test_strategy_yaml_unchanged_and_fingerprints_frozen():
    assert MANIFEST["strategy_yaml_modified"] is False
    actual = {name: fingerprint(load_strategy(
        ROOT / f"strategies/{name}/v0.2.0/strategy.yaml")) for name in STRATEGIES}
    assert actual == EXPECTED_FINGERPRINTS
    assert {name: item["fingerprint"] for name, item in MANIFEST["strategies"].items()} == actual


def test_human_decision_fields_and_checkboxes_remain_unset():
    decision = MANIFEST["human_decision"]
    assert decision["required"] is True
    assert all(decision[key] is None for key in (
        "decision", "decision_date", "allowed_next_action", "forbidden_next_action"))
    template = (ROOT / decision["decision_record"]).read_text(encoding="utf-8")
    assert template.count("[ ] CONTINUE_RESEARCH") == 3
    assert template.count("[ ] RETIRE") == 3
    assert template.count("[ ] KILL") == 3
    assert "[x]" not in template.lower()


def test_no_automatic_strategy_state_transition():
    assert MANIFEST["automatic_state_transition"] is False
    summary = (PACKET / "research_cycle_summary.md").read_text(encoding="utf-8")
    assert "No strategy state transition is authorized" in summary


def test_holdout_reveal_timing_is_recorded():
    phases = {item["phase"]: item for item in MANIFEST["research_phases"]}
    assert phases["3D-3"]["holdout_status"] == "pristine_at_execution_then_revealed"
    assert phases["3D-4"]["holdout_status"] == "revealed_holdout_after_3d3"
    assert MANIFEST["holdout_consumption"]["may_be_called_pristine_for_tuned_descendant"] is False


def test_retrospective_tuning_and_new_hypothesis_rules_documented():
    governance = (ROOT / "decisions/RESEARCH_GOVERNANCE.md").read_text(encoding="utf-8")
    assert "cannot be reused as pristine validation for a tuned descendant" in governance
    assert "pre-register the rationale" in governance
    assert "pre-register falsification criteria" in governance
    assert "new untouched validation resource" in governance


def test_factual_manifest_has_no_comparative_selection_fields():
    prohibited = {"rank", "winner", "best", "score", "approved", "rejected", "promotion"}

    def keys(value):
        if isinstance(value, dict):
            return set(value).union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value), set())
        return set()

    assert not prohibited.intersection(keys(MANIFEST))
