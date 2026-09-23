import pandas as pd
from tradingdyor.point_in_time import PointInTimeStore, Observation
from datetime import datetime, timezone

def test_point_in_time_excludes_future_observations():
    s=PointInTimeStore()
    s.add(Observation("ABC",datetime(2025,1,1,tzinfo=timezone.utc),"pe",10,"x","u"))
    s.add(Observation("ABC",datetime(2026,1,1,tzinfo=timezone.utc),"pe",20,"x","u"))
    rows=s.latest("ABC",datetime(2025,6,1,tzinfo=timezone.utc))
    assert rows[0].value==10

def test_forward_return():
    idx=pd.date_range("2025-01-01",periods=300,freq="D")
    prices=pd.Series(range(100,400),index=idx,dtype=float)
    result=PointInTimeStore().forward_return(prices,pd.Timestamp("2025-01-01"),1)
    assert result is not None and result>0
