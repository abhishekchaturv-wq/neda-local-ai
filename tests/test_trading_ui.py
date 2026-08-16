import unittest

from trading_ui import dashboard_payload


class TradingUIV1Tests(unittest.TestCase):
    def test_payload_contains_chain_analytics(self):
        data = dashboard_payload()
        self.assertEqual(data["symbol"], "NIFTY")
        self.assertEqual(data["mode"], "DEMO / PAPER ANALYSIS")
        self.assertIsNotNone(data["analytics"]["pcr_oi"])
        self.assertIsNotNone(data["analytics"]["max_pain"])
        self.assertGreater(len(data["strikes"]), 0)

    def test_ui_does_not_emit_live_order_signal(self):
        data = dashboard_payload()
        self.assertEqual(data["signal"]["state"], "WAIT")
        self.assertIsNone(data["signal"]["confidence"])
        self.assertIn("descriptive", data["signal"]["reason"])


if __name__ == "__main__":
    unittest.main()
