import unittest
from datetime import date

from market_data import DemoMarketDataProvider, MarketSnapshot


class MarketDataAdapterV1Tests(unittest.TestCase):
    def test_demo_provider_returns_coherent_snapshot(self):
        snap = DemoMarketDataProvider().snapshot("nifty")
        self.assertIsInstance(snap, MarketSnapshot)
        self.assertEqual(snap.symbol, "NIFTY")
        self.assertEqual(snap.expiry, date(2026, 8, 27))
        self.assertEqual(snap.underlying_price, 24520.0)
        self.assertEqual(len(snap.options), 14)

    def test_all_options_share_market_identity(self):
        snap = DemoMarketDataProvider().snapshot()
        self.assertTrue(all(o.contract.symbol == "NIFTY" for o in snap.options))
        self.assertTrue(all(o.contract.expiry == snap.expiry for o in snap.options))
        self.assertTrue(all(o.underlying_price == snap.underlying_price for o in snap.options))


if __name__ == "__main__":
    unittest.main()
