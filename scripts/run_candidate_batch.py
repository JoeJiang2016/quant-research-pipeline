"""Run registered candidates independently; never rank or select them."""
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from backtest.candidates import load_registry, registry_checksum
from scripts.run_backtest import build_result

def run_batch(registry_path=ROOT/"strategies/candidates.json", output_root=ROOT/"reports/candidates"):
    registry_path=Path(registry_path); candidates=load_registry(registry_path)
    try: commit=subprocess.check_output(["git","-c",f"safe.directory={ROOT}","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    except Exception: commit="uncommitted"
    checksum=registry_checksum(registry_path); batch_id=f"{commit[:12]}-{checksum[:12]}"; target=Path(output_root)/batch_id; target.mkdir(parents=True,exist_ok=True)
    identities=[]; summary=[]; datasets=set()
    for candidate in candidates:
        result=build_result(candidate["strategy_path"]); candidate_dir=target/candidate["strategy_id"]; candidate_dir.mkdir(parents=True,exist_ok=True)
        (candidate_dir/"backtest_result.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        metrics=result["metrics"]; datasets.add(result["dataset_id"])
        identities.append({"strategy_id":candidate["strategy_id"],"version":candidate["version"],"fingerprint":candidate["fingerprint"],"dataset_id":result["dataset_id"],"dataset_checksum":result["reproducibility"]["data_checksum_sha256"]})
        summary.append({"strategy_id":candidate["strategy_id"],"version":candidate["version"],"fingerprint":candidate["fingerprint"],"family":candidate["family"],"dataset_id":result["dataset_id"],"trade_count":metrics["trades"],"total_return":metrics["total_return"],"win_rate":metrics["win_rate"],"expectancy":metrics["expectancy"],"profit_factor":metrics["profit_factor"],"max_drawdown":metrics["max_drawdown"]})
    comparable=len(datasets)==1
    manifest={"batch_id":batch_id,"run_timestamp":datetime.now(timezone.utc).isoformat(),"git_commit":commit,"registry_checksum":checksum,"candidate_count":len(candidates),"candidates":identities,"comparable_performance":comparable,"comparison_note":None if comparable else "different smoke-test datasets"}
    (target/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    (target/"candidate_summary.json").write_text(json.dumps({"batch_id":batch_id,"comparable_performance":comparable,"comparison_note":manifest["comparison_note"],"candidates":summary},indent=2)+"\n",encoding="utf-8")
    print(target); return target
if __name__=="__main__": run_batch()
