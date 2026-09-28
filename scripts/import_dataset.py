import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from backtest.datasets import import_dataset

def parse_mapping(values):
    return {canonical:source for canonical,source in (item.split("=",1) for item in values)}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--input",required=True); parser.add_argument("--dataset-id",required=True); parser.add_argument("--version",default="1"); parser.add_argument("--symbol",required=True); parser.add_argument("--timeframe",required=True); parser.add_argument("--timezone"); parser.add_argument("--timestamp-semantics",choices=["instant","session_date"],default="instant"); parser.add_argument("--source",required=True); parser.add_argument("--price-adjustment",choices=["raw","split_adjusted","total_return_adjusted","provider_adjusted","unknown"],default="unknown"); parser.add_argument("--session-policy",default="unknown"); parser.add_argument("--asset-class",default="unknown"); parser.add_argument("--country",default="unknown"); parser.add_argument("--map",action="append",default=[])
    args=parser.parse_args(); mapping=parse_mapping(args.map) if args.map else None
    result=import_dataset(args.input,dataset_id=args.dataset_id,version=args.version,symbol=args.symbol,timeframe=args.timeframe,source_timezone=args.timezone,source=args.source,price_adjustment=args.price_adjustment,session_policy=args.session_policy,asset_class=args.asset_class,country=args.country,column_mapping=mapping,timestamp_semantics=args.timestamp_semantics)
    print(json.dumps({key:str(result[key]) for key in ("raw_path","processed_path","manifest_path","quality_path")},indent=2))
if __name__=="__main__": main()
