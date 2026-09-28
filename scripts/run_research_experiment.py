"""Run immutable strategies against one canonical experiment dataset."""
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from backtest.datasets import load_dataset
from backtest.experiments import comparable_performance, experiment_fingerprint, load_experiment
from backtest.strategy import fingerprint, load_strategy
from scripts.run_backtest import build_result

def _resolve(path):
    path=Path(path); return path if path.is_absolute() else ROOT/path

def run_experiment(experiment_path, output_root=ROOT/"reports/experiments"):
    experiment=load_experiment(experiment_path); manifest_path=_resolve(experiment["dataset"]["manifest_path"]); dataset_manifest=json.loads(manifest_path.read_text())
    if dataset_manifest["dataset_id"] != experiment["dataset"]["dataset_id"]: raise ValueError("experiment dataset identity does not match manifest")
    strategies=[]
    for reference in experiment["strategies"]:
        strategy_path=ROOT/"strategies"/reference["strategy_id"]/("v"+reference["strategy_version"])/"strategy.yaml"; strategy=load_strategy(strategy_path)
        if dataset_manifest["symbol"] not in strategy["universe"]: raise ValueError("dataset symbol is outside strategy universe")
        if dataset_manifest["timeframe"] != strategy["timeframe"]: raise ValueError("dataset timeframe is incompatible with strategy")
        strategies.append((strategy_path,strategy))
    processed_path=_resolve(dataset_manifest["processed_path"]); bars=load_dataset(processed_path,symbol=dataset_manifest["symbol"],timeframe=dataset_manifest["timeframe"],timestamp_semantics=dataset_manifest.get("timestamp_semantics","instant"))
    start,end=experiment["research_window"]["start"],experiment["research_window"]["end"]; bars=[bar for bar in bars if start <= bar["timestamp"] <= end]
    if not bars: raise ValueError("research window contains no dataset bars")
    try: commit=subprocess.check_output(["git","-c",f"safe.directory={ROOT}","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    except Exception: commit="uncommitted"
    exp_fp=experiment_fingerprint(experiment); run_id=f"{commit[:12]}-{exp_fp[:12]}"; target=Path(output_root)/experiment["experiment_id"]/run_id; target.mkdir(parents=True,exist_ok=True)
    identities=[]; summary=[]; comparison_records=[]
    dataset_identity={"dataset_id":dataset_manifest["dataset_id"],"data_version":dataset_manifest["dataset_version"],"data_checksum_sha256":dataset_manifest["processed_file_sha256"]}
    for strategy_path,strategy in strategies:
        result=build_result(strategy_path,bars=bars,dataset_identity=dataset_identity); directory=target/strategy["strategy_id"]; directory.mkdir(parents=True,exist_ok=True); (directory/"backtest_result.json").write_text(json.dumps(result,indent=2)+"\n")
        identities.append({"strategy_id":strategy["strategy_id"],"version":strategy["strategy_version"],"fingerprint":fingerprint(strategy)})
        metrics=result["metrics"]; summary.append({"strategy_id":strategy["strategy_id"],"version":strategy["strategy_version"],"fingerprint":fingerprint(strategy),"dataset_id":result["dataset_id"],"trade_count":metrics["trades"],"total_return":metrics["total_return"],"win_rate":metrics["win_rate"],"expectancy":metrics["expectancy"],"profit_factor":metrics["profit_factor"],"max_drawdown":metrics["max_drawdown"]})
        comparison_records.append({"dataset_checksum":dataset_manifest["processed_file_sha256"],"research_window":experiment["research_window"],"timeframe":dataset_manifest["timeframe"],"cost_scenario":experiment["cost_sensitivity"]["scenarios"][0]})
    comparable=comparable_performance(comparison_records)
    manifest={"experiment_id":experiment["experiment_id"],"experiment_version":experiment["experiment_version"],"experiment_fingerprint":exp_fp,"git_commit":commit,"dataset":{"dataset_id":dataset_manifest["dataset_id"],"version":dataset_manifest["dataset_version"],"checksum":dataset_manifest["processed_file_sha256"]},"strategies":identities,"research_window":experiment["research_window"],"evaluation":experiment["evaluation"],"walk_forward":experiment["walk_forward"],"cost_sensitivity":experiment["cost_sensitivity"],"run_timestamp":datetime.now(timezone.utc).isoformat(),"comparable_performance":comparable}
    (target/"experiment_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n"); (target/"candidate_summary.json").write_text(json.dumps({"comparable_performance":comparable,"candidates":summary},indent=2)+"\n"); print(target); return target
if __name__=="__main__": run_experiment(sys.argv[1])
