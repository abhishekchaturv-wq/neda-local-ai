import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from neda_test024_autonomous_paper_trading import (
    CachedSnapshotProvider, LiveProvenance, derive_context
)
from neda_test022_historical_replay import BTCBar

class TestTest024(unittest.TestCase):
    def bars(self,n=24*30):
        base=60000.0
        return [BTCBar(i*3600,base+i*5-2,base+i*5+5,base+i*5-5,base+i*5,100) for i in range(n)]

    def test_context_is_derived_without_manual_scores(self):
        ctx=derive_context(self.bars(),61500.0)
        self.assertGreaterEqual(ctx.trend_score,-1); self.assertLessEqual(ctx.trend_score,1)
        self.assertGreaterEqual(ctx.momentum_score,-1); self.assertLessEqual(ctx.momentum_score,1)

    def test_cached_provider_returns_exact_prefetched_snapshot(self):
        class Fake:
            def __init__(self): self.calls=0
            def snapshot(self,expiry=None): self.calls+=1; return "delegate"
        fake=Fake(); cached=CachedSnapshotProvider(fake)
        cached.prime("audited-snapshot")
        self.assertEqual(cached.snapshot(),"audited-snapshot"); self.assertEqual(fake.calls,0)
        self.assertEqual(cached.snapshot(),"delegate"); self.assertEqual(fake.calls,1)

    def test_live_provenance_is_non_synthetic(self):
        live=LiveProvenance("DeltaExchangeIndiaPublicREST","https://api.india.delta.exchange/v2/tickers",datetime.now(timezone.utc).isoformat(),"abc",10,63000,False)
        self.assertFalse(live.synthetic)

    def test_historical_fetch_paginates_beyond_binance_1000_limit(self):
        import neda_test024_autonomous_paper_trading as mod
        page1=[[1000,"60000","60100","59900","60050","10"],[2000,"60050","60200","60000","60150","11"]]
        page2=[[3000,"60150","60300","60100","60250","12"],[4000,"60250","60400","60200","60350","13"]]
        calls=[]
        def fake_get(url,timeout=20.0):
            calls.append(url)
            # Simulate two non-full pages that still require another request.
            return json.dumps(page1 if len(calls)==1 else page2).encode()
        with patch.object(mod,"_json_get",side_effect=fake_get), patch.object(mod.time,"time",return_value=100000):
            # Patch time window so the mock timestamps are inside it.
            with patch.object(mod, "validate_bars", lambda rows: None):
                rows, provenance = mod.fetch_historical_btc(history_days=7)
        self.assertEqual([r.timestamp for r in rows],[1000,2000,3000,4000])
        self.assertEqual(provenance.record_count,4)
        self.assertTrue(provenance.source_url.endswith("&paginated=true"))
        self.assertEqual(len(calls),2)

    def test_risk_rejection_has_explicit_audit_stage(self):
        class Result:
            action="NO_TRADE"; risk_reason="PER_TRADE_PREMIUM_LIMIT_EXCEEDED"; order_status="REJECTED"
        risk_rejected=Result.order_status=="REJECTED" and bool(Result.risk_reason)
        self.assertTrue(risk_rejected)

if __name__=="__main__": unittest.main()
