"""Run the self-contained Phase 2A synthetic-data walk-forward demonstration."""
import argparse, copy, json, sys
from datetime import date, timedelta, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
import yaml
from backtest.datasets import create_manifest, load_dataset, write_manifest
from backtest.engine.core import metrics, run
from backtest.validation import validate_strategy
from backtest.strategy import load_strategy, fingerprint
from backtest.walk_forward import build_folds, stitched_oos_equity

def synthetic_demo(path, rows=80):
    """Create deterministic *demo/test* data; no market data or network access."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines=["timestamp,open,high,low,close,volume,symbol"]
    start=date(2020,1,1)
    for i in range(rows):
        # Each 24-bar cycle has 20 quiet bars, a breakout, next-open entry,
        # and a target hit. This exercises execution, not strategy selection.
        phase=i % 24
        if phase == 0: opening,high,low,close=100,105.5,99.5,105
        elif phase == 1: opening,high,low,close=105,106.5,104.5,106
        elif phase == 2: opening,high,low,close=106,112,105,110
        else: opening,high,low,close=100,100.5,99.5,100
        lines.append(f"{start+timedelta(days=i)}T00:00:00+00:00,{opening:.2f},{high:.2f},{low:.2f},{close:.2f},1000,DEMO")
    path.write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--strategy",required=True); ap.add_argument("--dataset",default=str(ROOT/"data/processed/demo_breakout_trades.synthetic.csv")); ap.add_argument("--train-bars",type=int,default=28); ap.add_argument("--test-bars",type=int,default=24); ap.add_argument("--anchored",action="store_true")
    args=ap.parse_args(); dataset=Path(args.dataset); synthetic_demo(dataset)
    strategy=load_strategy(args.strategy)
    bars=load_dataset(dataset,symbol=strategy["universe"][0],timeframe=strategy["timeframe"])
    manifest=create_manifest(dataset,dataset_id="DEMO_1D_synthetic_v1",symbol="DEMO",timeframe=strategy["timeframe"],timezone="UTC",source="synthetic/demo",price_adjustment="unknown")
    target=ROOT/"reports/walk_forward"/strategy["strategy_id"]; (target/"folds").mkdir(parents=True,exist_ok=True); write_manifest(target/"manifest.json",manifest)
    folds=build_folds(len(bars),train_bars=args.train_bars,test_bars=args.test_bars,anchored=args.anchored)
    curves=[]; fold_results=[]; fold_exposure_bars=[]
    for fold in folds:
        # OOS run starts at its boundary; fixed parameters and no future bars are supplied.
        oos=bars[fold.test_start:fold.test_end]; result=run(strategy,oos); result_metrics=metrics(result,strategy["risk"]["initial_equity"])
        payload={"fold_id":fold.fold_id,"strategy_id":strategy["strategy_id"],"strategy_version":strategy["strategy_version"],"strategy_fingerprint":fingerprint(strategy),"train_start":bars[fold.train_start]["timestamp"],"train_end":bars[fold.train_end-1]["timestamp"],"test_start":oos[0]["timestamp"],"test_end":oos[-1]["timestamp"],"dataset_version":manifest["version"],"metrics":result_metrics,"trade_log":result["trades"],"warnings":["price_adjustment is unknown; results are not adjusted-action assumptions"]}
        (target/"folds"/(fold.fold_id+".json")).write_text(json.dumps(payload,indent=2)+"\n"); fold_results.append(payload); curves.append(result["equity_curve"]); fold_exposure_bars.append(result["exposure_bars"])
    stitched=stitched_oos_equity(curves); stitched_trades=[trade for fold in fold_results for trade in fold["trade_log"]]
    for fold in fold_results:
        if any(not (fold["test_start"] <= trade["entry_time"] <= fold["test_end"] and fold["test_start"] <= trade["exit_time"] <= fold["test_end"]) for trade in fold["trade_log"]): raise AssertionError("IS trade leaked into OOS output")
    combined=metrics({"trades":stitched_trades,"equity_curve":stitched,"commission":sum(t["commission"] for t in stitched_trades),"slippage":0,"exposure_bars":sum(fold_exposure_bars)},strategy["risk"]["initial_equity"])
    summary={"total_folds":len(folds),"oos_trade_count":len(stitched_trades),"combined_oos_return":combined["total_return"],"oos_max_drawdown":combined["max_drawdown"],"oos_profit_factor":combined["profit_factor"],"oos_expectancy":combined["expectancy"],"fold_to_fold_variation":{"return_range":[min(x["metrics"]["total_return"] for x in fold_results),max(x["metrics"]["total_return"] for x in fold_results)]},"adjustment_warning":"unknown"}
    (target/"walk_forward_summary.json").write_text(json.dumps(summary,indent=2)+"\n"); (target/"stitched_oos_equity.json").write_text(json.dumps(stitched,indent=2)+"\n"); (target/"stitched_oos_trade_log.json").write_text(json.dumps(stitched_trades,indent=2)+"\n")
    scenarios={}
    for name,commission,slippage in [("base",1,1),("slippage_1_5x",1,1.5),("slippage_2x",1,2),("commission_2x",2,1)]:
        candidate=copy.deepcopy(strategy); candidate["execution"]["commission_per_trade"]*=commission; candidate["execution"]["slippage_bps"]*=slippage
        result=run(candidate,bars[folds[0].test_start:folds[0].test_end]); m=metrics(result,candidate["risk"]["initial_equity"]); scenarios[name]={key:m[key] for key in ("profit_factor","expectancy","max_drawdown","total_return")}
    (target/"cost_sensitivity.json").write_text(json.dumps(scenarios,indent=2)+"\n"); print(target)
if __name__=="__main__": main()
