import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import yaml
from backtest.engine.core import run, metrics
from backtest.data import checksum, load_bars
from backtest.validation import validate_result, validate_strategy
from backtest.strategy import fingerprint, load_strategy

# Backward-compatible public name used by existing integrations and tests.
validate = validate_strategy
def build_result(file, *, bars=None, dataset_identity=None):
    s=load_strategy(file)
    if bars is None:
        data_path=ROOT/"data"/(s["dataset_id"]+".csv"); bars=load_bars(data_path)
        dataset_identity={"dataset_id":s["dataset_id"],"data_version":data_path.name,"data_checksum_sha256":checksum(data_path)}
    else:
        dataset_identity=dict(dataset_identity or {})
        for key in ("dataset_id","data_version","data_checksum_sha256"):
            if key not in dataset_identity: raise ValueError(f"dataset identity missing {key}")
    result=run(s,bars)
    try: commit=subprocess.check_output(["git","-c",f"safe.directory={ROOT}","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    except Exception: commit="uncommitted"
    out={"strategy_id":s["strategy_id"],"strategy_version":s["strategy_version"],"strategy_fingerprint":fingerprint(s),"dataset_id":dataset_identity["dataset_id"],"period":{"start":bars[0]["timestamp"],"end":bars[-1]["timestamp"]},"metrics":metrics(result,s["risk"]["initial_equity"]),"equity_curve":result["equity_curve"],"trade_log":result["trades"],"parameter_snapshot":s,"execution_assumptions":{"signal_time":"bar_close","fill_time":"next_bar_open","same_bar_stop_target":"stop_first"},"reproducibility":{"git_commit":commit,"data_version":dataset_identity["data_version"],"data_checksum_sha256":dataset_identity["data_checksum_sha256"],"timestamp":datetime.now(timezone.utc).isoformat(),"engine_version":"1.1.0"}}
    validate_result(out)
    return out
def main(file):
    out=build_result(file); result=out["trade_log"]; s=out["parameter_snapshot"]
    target=ROOT/"reports"/s["strategy_id"]; target.mkdir(parents=True,exist_ok=True)
    (target/"backtest_result.json").write_text(json.dumps(out,indent=2)); (target/"trade_log.json").write_text(json.dumps(result,indent=2)); print(target)
if __name__=="__main__": main(sys.argv[1])
