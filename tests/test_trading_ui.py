import unittest

from trading_ui import dashboard_payload


class TradingUIV1Tests(unittest.TestCase):
    def test_payload_contains_provider(self):
        data = dashboard_payload()
        self.assertEqual(data["provider"], "DemoMarketDataProvider")
        self.assertEqual(data["symbol"], "NIFTY")
        self.assertEqual(data["mode"], "DEMO / PAPER ANALYSIS")

    def test_payload_contains_chain_analytics(self):
        data = dashboard_payload()
        self.assertIsNotNone(data["analytics"]["pcr_oi"])
        self.assertIsNotNone(data["analytics"]["max_pain"])
        self.assertGreater(len(data["strikes"]), 0)

    def test_ui_stays_non_executing(self):
        data = dashboard_payload()
        self.assertEqual(data["signal"]["state"], "WAIT")
        self.assertIsNone(data["signal"]["confidence"])


if __name__ == "__main__":
    unittest.main()
