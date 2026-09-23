import json
from tradingdyor.collector import collect_all

if __name__ == "__main__":
    print(json.dumps([x.model_dump(mode="json") if hasattr(x,"model_dump") else x for x in collect_all()], indent=2))
