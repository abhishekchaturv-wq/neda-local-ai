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

    def test_historical_fetch_paginates_beyond_binance_1000_limit(self):
        import neda_test024_autonomous_paper_trading as mod

        page2 = [
            [1000, "60000", "60100", "59900", "60050", "10"],
            [2000, "60050", "60200", "60000", "60150", "11"],
        ]
        page1 = [
            [3000, "60150", "60300", "60100", "60250", "12"],
            [4000, "60250", "60400", "60200", "60350", "13"],
        ]

        calls = []

        def fake_get(url, timeout=20.0):
            calls.append(url)
            return json.dumps(page2 if len(calls) == 1 else page1).encode()

        with patch.object(mod, "_json_get", side_effect=fake_get), \
             patch.object(mod.time, "time", return_value=4.0):
            rows, provenance = mod.fetch_historical_btc(history_days=7)

        self.assertEqual([r.timestamp for r in rows], [1000, 2000, 3000, 4000])
        self.assertEqual(provenance.record_count, 4)
        self.assertTrue(provenance.source_url.endswith("&paginated=true"))
        self.assertEqual(len(calls), 2)

    def test_risk_rejection_has_explicit_audit_stage(self):
        class Result:
            action = "NO_TRADE"
            trade_id = None
            symbol = "BTC|2026-08-28|68000|PUT"
            decision_reason = "QUALIFIED_BUYER_CANDIDATE"
            entry_reason = "QUALIFIED_BUYER_CANDIDATE"
            selection_reason = "DIRECTIONAL+LIQUIDITY+MONEYNESS+EXPIRY"
            risk_reason = "PER_TRADE_PREMIUM_LIMIT_EXCEEDED"
            order_status = "REJECTED"
            fill_price = None

        risk_rejected = Result.order_status == "REJECTED" and bool(Result.risk_reason)
        self.assertTrue(risk_rejected)
        self.assertEqual(
            f"RISK_REJECTED:{Result.risk_reason}",
            "RISK_REJECTED:PER_TRADE_PREMIUM_LIMIT_EXCEEDED",
        )


if __name__ == "__main__":
    unittest.main()
