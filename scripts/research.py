import argparse, json
from tradingdyor.research_engine import research_universe

p=argparse.ArgumentParser()
p.add_argument("tickers",nargs="+")
args=p.parse_args()
print(json.dumps(research_universe(args.tickers),indent=2))
