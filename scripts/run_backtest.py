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

# Backward-compatible public name used by existing integrations and tests.
validate = validate_strategy
def main(file):
    with open(file) as f: s=yaml.safe_load(f)
    validate_strategy(s); data_path=ROOT/"data"/(s["dataset_id"]+".csv"); bars=load_bars(data_path)
    minimum = max(s["entry"]["lookback_bars"], s["exit"]["atr_period"]) + 2
    if len(bars) < minimum: raise ValueError(f"insufficient history: need at least {minimum} bars")
    result=run(s,bars)
    try: commit=subprocess.check_output(["git","-c",f"safe.directory={ROOT}","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    except Exception: commit="uncommitted"
    out={"strategy_id":s["strategy_id"],"strategy_version":s["strategy_version"],"dataset_id":s["dataset_id"],"period":{"start":bars[0]["timestamp"],"end":bars[-1]["timestamp"]},"metrics":metrics(result,s["risk"]["initial_equity"]),"equity_curve":result["equity_curve"],"trade_log":result["trades"],"parameter_snapshot":s,"execution_assumptions":{"signal_time":"bar_close","fill_time":"next_bar_open","same_bar_stop_target":"stop_first"},"reproducibility":{"git_commit":commit,"data_version":data_path.name,"data_checksum_sha256":checksum(data_path),"timestamp":datetime.now(timezone.utc).isoformat(),"engine_version":"1.1.0"}}
    validate_result(out)
    target=ROOT/"reports"/s["strategy_id"]; target.mkdir(parents=True,exist_ok=True)
    (target/"backtest_result.json").write_text(json.dumps(out,indent=2)); (target/"trade_log.json").write_text(json.dumps(result["trades"],indent=2)); print(target)
if __name__=="__main__": main(sys.argv[1])
