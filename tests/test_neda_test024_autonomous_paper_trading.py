import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from neda_test024_autonomous_paper_trading import (
    AuditedDeltaClient,
    CachedSnapshotProvider,
    DerivedContext,
    HistoricalProvenance,
    LiveProvenance,
    derive_context,
)
from neda_test022_historical_replay import BTCBar


class TestTest024(unittest.TestCase):
    def bars(self, n=24 * 30):
        base = 60000.0
        rows = []
        for i in range(n):
            close = base + i * 5.0
            rows.append(BTCBar(i * 3600, close - 2, close + 5, close - 5, close, 100))
        return rows

    def test_context_is_derived_without_manual_scores(self):
        ctx = derive_context(self.bars(), 61500.0)
        self.assertGreaterEqual(ctx.trend_score, -1)
        self.assertLessEqual(ctx.trend_score, 1)
        self.assertGreaterEqual(ctx.momentum_score, -1)
        self.assertLessEqual(ctx.momentum_score, 1)
        self.assertEqual(ctx.method, "7D_RANGE+30D_MEAN+6H_24H_RETURN_VOL_NORMALIZATION")

    def test_cached_provider_returns_exact_prefetched_snapshot(self):
        class Fake:
            def __init__(self):
                self.calls = 0
            def snapshot(self, expiry=None):
                self.calls += 1
                return "delegate"

        fake = Fake()
        cached = CachedSnapshotProvider(fake)
        cached.prime("audited-snapshot")
        self.assertEqual(cached.snapshot(), "audited-snapshot")
        self.assertEqual(fake.calls, 0)
        self.assertEqual(cached.snapshot(), "delegate")
        self.assertEqual(fake.calls, 1)

    def test_live_provenance_is_non_synthetic(self):
        live = LiveProvenance(
            source="DeltaExchangeIndiaPublicREST",
            source_url="https://api.india.delta.exchange/v2/tickers",
            observed_at=datetime.now(timezone.utc).isoformat(),
            raw_sha256="abc",
            option_count=10,
            underlying_price=63000,
            synthetic=False,
        )
        self.assertFalse(live.synthetic)
        self.assertEqual(live.option_count, 10)


if __name__ == "__main__":
    unittest.main()
