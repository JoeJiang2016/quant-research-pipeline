"""Run independent flat-start IS and OOS evaluations on one canonical dataset."""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.compatibility import strategy_dataset_compatibility
from backtest.datasets import load_dataset
from backtest.experiments import comparable_performance, experiment_fingerprint, load_experiment
from backtest.strategy import fingerprint, load_strategy
from scripts.run_backtest import build_result

WARMUP_POLICY = "pre_segment_history_for_indicators_only_no_signals_fills_or_pnl"
BOUNDARY_MODE = "flat_start"


def _resolve(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def evaluation_indices(bars, window):
    timestamps = [bar["timestamp"] for bar in bars]
    eligible = [index for index, stamp in enumerate(timestamps)
                if window["start"] <= stamp <= window["end"]]
    if not eligible:
        raise ValueError("evaluation window contains no dataset bars")
    start, end = eligible[0], eligible[-1]
    if start > end:
        raise ValueError("evaluation start must not exceed end")
    return start, end


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT}", "rev-parse", "HEAD"],
            cwd=ROOT, text=True).strip()
    except Exception:
        return "uncommitted"


def run_experiment(experiment_path, output_root=ROOT / "reports/experiments"):
    experiment = load_experiment(experiment_path)
    if experiment["walk_forward"]["enabled"]:
        raise ValueError("fixed-boundary experiment runner requires walk_forward.enabled=false")
    manifest_path = _resolve(experiment["dataset"]["manifest_path"])
    dataset_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if dataset_manifest["dataset_id"] != experiment["dataset"]["dataset_id"]:
        raise ValueError("experiment dataset identity does not match manifest")
    strategies = []
    for reference in experiment["strategies"]:
        strategy_path = (ROOT / "strategies" / reference["strategy_id"] /
                         ("v" + reference["strategy_version"]) / "strategy.yaml")
        strategy = load_strategy(strategy_path)
        compatibility = strategy_dataset_compatibility(strategy, dataset_manifest)
        if not compatibility["compatible"]:
            raise ValueError("strategy/dataset incompatibility: " +
                             "; ".join(compatibility["reasons"]))
        strategies.append((strategy_path, strategy))
    processed_path = _resolve(dataset_manifest["processed_path"])
    all_bars = load_dataset(
        processed_path, symbol=dataset_manifest["symbol"],
        timeframe=dataset_manifest["timeframe"],
        timestamp_semantics=dataset_manifest.get("timestamp_semantics", "instant"))
    research = experiment["research_window"]
    bars = [bar for bar in all_bars
            if research["start"] <= bar["timestamp"] <= research["end"]]
    if not bars:
        raise ValueError("research window contains no dataset bars")

    commit = _git_commit()
    experiment_fp = experiment_fingerprint(experiment)
    run_id = f"{commit[:12]}-{experiment_fp[:12]}"
    target = Path(output_root) / experiment["experiment_id"] / run_id
    target.mkdir(parents=True, exist_ok=True)
    dataset_identity = {
        "dataset_id": dataset_manifest["dataset_id"],
        "data_version": dataset_manifest["dataset_version"],
        "data_checksum_sha256": dataset_manifest["processed_file_sha256"],
    }
    experiment_identity = {
        "experiment_id": experiment["experiment_id"],
        "experiment_version": experiment["experiment_version"],
        "experiment_fingerprint": experiment_fp,
    }
    segment_records = {"IS": [], "OOS": []}
    summaries = []
    identities = []
    for strategy_path, strategy in strategies:
        strategy_fp = fingerprint(strategy)
        identities.append({"strategy_id": strategy["strategy_id"],
                           "version": strategy["strategy_version"],
                           "fingerprint": strategy_fp})
        strategy_summary = {
            "strategy_id": strategy["strategy_id"],
            "version": strategy["strategy_version"],
            "fingerprint": strategy_fp,
            "costs": {"commission_per_trade": strategy["execution"]["commission_per_trade"],
                      "slippage_bps": strategy["execution"]["slippage_bps"]},
        }
        strategy_dir = target / strategy["strategy_id"]
        strategy_dir.mkdir(parents=True, exist_ok=True)
        for segment, key in (("IS", "in_sample"), ("OOS", "out_of_sample")):
            window = experiment["evaluation"][key]
            start_index, end_index = evaluation_indices(bars, window)
            evaluation = {"segment": segment, "start": window["start"],
                          "end": window["end"], "start_index": start_index,
                          "end_index": end_index, "warmup_policy": WARMUP_POLICY,
                          "boundary_mode": BOUNDARY_MODE}
            result = build_result(
                strategy_path, bars=bars, dataset_identity=dataset_identity,
                evaluation=evaluation, experiment_identity=experiment_identity)
            (strategy_dir / f"{segment.lower()}_result.json").write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8")
            strategy_summary[f"{segment.lower()}_metrics"] = result["metrics"]
            segment_records[segment].append({
                "dataset_checksum": dataset_manifest["processed_file_sha256"],
                "research_window": window,
                "timeframe": dataset_manifest["timeframe"],
                "cost_scenario": strategy_summary["costs"],
            })
        summaries.append(strategy_summary)

    comparability = {segment: comparable_performance(records)
                     for segment, records in segment_records.items()}
    manifest = {
        **experiment_identity,
        "git_commit": commit,
        "dataset": {"dataset_id": dataset_manifest["dataset_id"],
                    "version": dataset_manifest["dataset_version"],
                    "checksum": dataset_manifest["processed_file_sha256"]},
        "strategies": identities,
        "research_window": research,
        "evaluation": experiment["evaluation"],
        "warmup_policy": WARMUP_POLICY,
        "boundary_mode": BOUNDARY_MODE,
        "walk_forward": experiment["walk_forward"],
        "cost_source": "canonical_strategy_execution_fields",
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "comparability_by_segment": comparability,
        "comparable_performance": all(comparability.values()),
        "cross_segment_comparison": False,
    }
    (target / "experiment_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (target / "baseline_summary.json").write_text(
        json.dumps({"experiment_id": experiment["experiment_id"],
                    "comparability_by_segment": comparability,
                    "cross_segment_comparison": False,
                    "strategies": summaries}, indent=2) + "\n", encoding="utf-8")
    print(target)
    return target


if __name__ == "__main__":
    run_experiment(sys.argv[1])
