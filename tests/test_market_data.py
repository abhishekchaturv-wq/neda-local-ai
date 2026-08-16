import unittest
from datetime import date
import time

from market_data import DemoMarketDataProvider, MarketSnapshot


class MarketDataAdapterV1_1Tests(unittest.TestCase):
    def test_demo_nifty_snapshot(self):
        snap = DemoMarketDataProvider().snapshot("nifty")
        self.assertIsInstance(snap, MarketSnapshot)
        self.assertEqual(snap.symbol, "NIFTY")
        self.assertEqual(snap.asset_class, "INDEX")
        self.assertEqual(snap.expiry, date(2026, 8, 27))
        self.assertFalse(snap.live)
        self.assertFalse(snap.is_stale)

    def test_demo_btc_option_snapshot(self):
        snap = DemoMarketDataProvider().snapshot("btc")
        self.assertEqual(snap.symbol, "BTC")
        self.assertEqual(snap.asset_class, "CRYPTO")
        self.assertEqual(snap.expiry, date(2026, 8, 28))
        self.assertGreater(snap.underlying_price, 0)
        self.assertGreater(len(snap.options), 0)
        self.assertTrue(all(o.contract.symbol == "BTC" for o in snap.options))

    def test_unsupported_symbol_is_rejected(self):
        with self.assertRaises(ValueError):
            DemoMarketDataProvider().snapshot("ETH")

    def test_stale_detection(self):
        snap = MarketSnapshot(
            symbol="BTC",
            asset_class="CRYPTO",
            expiry=date(2026, 8, 28),
            underlying_price=118500.0,
            options=(),
            observed_at_epoch=time.time() - 100,
            provider_name="TestProvider",
            live=True,
            stale_after_seconds=30,
        )
        self.assertTrue(snap.is_stale)

    def test_market_identity_is_coherent(self):
        for symbol in ("NIFTY", "BTC"):
            snap = DemoMarketDataProvider().snapshot(symbol)
            self.assertTrue(all(o.contract.symbol == snap.symbol for o in snap.options))
            self.assertTrue(all(o.contract.expiry == snap.expiry for o in snap.options))
            self.assertTrue(all(o.underlying_price == snap.underlying_price for o in snap.options))


if __name__ == "__main__":
    unittest.main()
