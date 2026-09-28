import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from backtest.strategy import compare, load_strategy
if __name__=="__main__":
    left,right=map(load_strategy,sys.argv[1:3]); print(json.dumps({"strategy_id":left["strategy_id"],"from":left["strategy_version"],"to":right["strategy_version"],"changed":compare(left,right)},indent=2))
