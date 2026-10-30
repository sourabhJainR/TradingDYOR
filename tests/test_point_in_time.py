from datetime import datetime, timezone
import tempfile
from pathlib import Path
import unittest
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from tradingdyor.point_in_time import Observation, PointInTimeStore


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


class PointInTimeStoreTests(unittest.TestCase):
    def test_historical_query_uses_source_availability_not_retrieval_time(self):
        store = PointInTimeStore()
        try:
            store.add(Observation(
                ticker="ABC", as_of=dt("2026-06-01T12:00:00"),
                metric="pe", value=10.0, source="market-data",
                source_url="https://data.example/abc",
                available_at=dt("2026-05-01T00:00:00"),
                retrieved_at=dt("2026-06-01T12:00:00"),
            ))
            store.add(Observation(
                ticker="ABC", as_of=dt("2026-07-02T12:00:00"),
                metric="pe", value=20.0, source="market-data",
                source_url="https://data.example/abc",
                available_at=dt("2026-07-01T00:00:00"),
                retrieved_at=dt("2026-07-02T12:00:00"),
            ))

            june = store.latest("ABC", dt("2026-06-30T23:59:59"))
            july = store.latest("ABC", dt("2026-07-31T23:59:59"))
            self.assertEqual(june[0].value, 10.0)
            self.assertEqual(july[0].value, 20.0)
        finally:
            store.close()

    def test_retrieval_time_alone_never_makes_unknown_evidence_available(self):
        store = PointInTimeStore()
        try:
            store.add(Observation(
                ticker="ABC", as_of=dt("2026-06-01T12:00:00"),
                metric="news_tone", value=3.2, source="news",
                source_url="https://news.example/story",
                retrieved_at=dt("2026-06-01T12:00:00"),
            ))
            self.assertEqual(store.latest("ABC", dt("2026-06-02T00:00:00")), [])
        finally:
            store.close()

    def test_publication_and_observation_times_are_fallbacks_but_remain_distinct(self):
        store = PointInTimeStore()
        try:
            store.add(Observation(
                ticker="ABC", as_of=dt("2026-06-01T12:00:00"),
                metric="published_metric", value=1, source="news",
                source_url="https://news.example/published",
                published_at=dt("2026-05-20T00:00:00"),
                retrieved_at=dt("2026-06-01T12:00:00"),
            ))
            store.add(Observation(
                ticker="ABC", as_of=dt("2026-06-01T12:00:00"),
                metric="observed_metric", value=2, source="news",
                source_url="https://news.example/observed",
                observed_at=dt("2026-05-25T00:00:00"),
                retrieved_at=dt("2026-06-01T12:00:00"),
            ))
            rows = {row.metric: row for row in store.latest("ABC", dt("2026-05-30T00:00:00"))}
            self.assertEqual(rows["published_metric"].published_at, dt("2026-05-20T00:00:00"))
            self.assertIsNone(rows["published_metric"].available_at)
            self.assertEqual(rows["observed_metric"].observed_at, dt("2026-05-25T00:00:00"))
            self.assertIsNone(rows["observed_metric"].available_at)
        finally:
            store.close()

    def test_future_available_evidence_is_excluded(self):
        store = PointInTimeStore()
        try:
            store.add(Observation(
                ticker="ABC", as_of=dt("2026-06-01T12:00:00"),
                metric="future_metric", value=99, source="filing",
                source_url="https://sec.example/filing",
                available_at=dt("2026-07-01T00:00:00"),
                retrieved_at=dt("2026-06-01T12:00:00"),
            ))
            self.assertEqual(store.latest("ABC", dt("2026-06-30T23:59:59")), [])
        finally:
            store.close()

    def test_sqlite_store_persists_and_deduplicates_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data" / "observations.sqlite"
            row = Observation(
                ticker="ABC", as_of=dt("2026-06-01T12:00:00"),
                metric="price", value=12.5, source="market-data",
                source_url="https://data.example/abc",
                available_at=dt("2026-06-01T12:00:00"),
                retrieved_at=dt("2026-06-01T12:01:00"),
                provider="example", extraction_version="v1",
            )
            store = PointInTimeStore(path)
            self.assertTrue(store.add(row))
            self.assertFalse(store.add(row))
            store.close()

            reopened = PointInTimeStore(path)
            try:
                result = reopened.latest("ABC", dt("2026-06-02T00:00:00"))
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0].value, 12.5)
                self.assertEqual(result[0].provider, "example")
                self.assertEqual(result[0].extraction_version, "v1")
            finally:
                reopened.close()

    def test_forward_return_enters_on_next_session_to_avoid_same_day_lookahead(self):
        prices = pd.Series(
            [100.0, 110.0, 150.0],
            index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-02-01"]),
        )
        store = PointInTimeStore()
        try:
            result = store.forward_return(prices, pd.Timestamp("2026-01-01"), months=1)
            self.assertAlmostEqual(result, 150.0 / 110.0 - 1.0)
            same_day = store.forward_return(
                prices, pd.Timestamp("2026-01-01"), months=1, entry_lag_sessions=0,
            )
            self.assertAlmostEqual(same_day, 150.0 / 100.0 - 1.0)
        finally:
            store.close()

    def test_forward_return_rejects_invalid_lag_and_horizon(self):
        store = PointInTimeStore()
        try:
            prices = pd.Series([10.0], index=pd.to_datetime(["2026-01-01"]))
            with self.assertRaises(ValueError):
                store.forward_return(prices, pd.Timestamp("2026-01-01"), entry_lag_sessions=-1)
            with self.assertRaises(ValueError):
                store.forward_return(prices, pd.Timestamp("2026-01-01"), months=0)
            self.assertIsNone(store.forward_return(
                prices, pd.Timestamp("2026-01-01"), months=1, entry_lag_sessions=1,
            ))
        finally:
            store.close()


    def test_concurrent_duplicate_ingestion_is_idempotent_across_connections(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.sqlite"
            first = PointInTimeStore(path)
            second = PointInTimeStore(path)
            row = Observation(
                ticker="ABC", as_of=dt("2026-06-01T12:00:00"),
                metric="price", value=12.5, source="market-data",
                source_url="https://data.example/abc",
                available_at=dt("2026-06-01T12:00:00"),
            )
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(lambda store: store.add(row), (first, second)))
                self.assertEqual(sorted(results), [False, True])
                self.assertEqual(len(first.latest("ABC", dt("2026-06-02T00:00:00"))), 1)
            finally:
                first.close()
                second.close()



if __name__ == "__main__":
    unittest.main()
