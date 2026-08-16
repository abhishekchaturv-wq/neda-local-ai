import unittest

from trading_ui import dashboard_payload


class TradingUIV1_1Tests(unittest.TestCase):
    def test_nifty_payload_reports_provider_and_status(self):
        data = dashboard_payload("NIFTY")
        self.assertEqual(data["provider"], "DemoMarketDataProvider")
        self.assertEqual(data["data_status"], "DEMO")
        self.assertEqual(data["symbol"], "NIFTY")

    def test_btc_payload_is_supported(self):
        data = dashboard_payload("BTC")
        self.assertEqual(data["symbol"], "BTC")
        self.assertEqual(data["asset_class"], "CRYPTO")
        self.assertEqual(data["data_status"], "DEMO")
        self.assertGreater(len(data["strikes"]), 0)

    def test_ui_stays_non_executing(self):
        for symbol in ("NIFTY", "BTC"):
            data = dashboard_payload(symbol)
            self.assertEqual(data["signal"]["state"], "WAIT")
            self.assertIsNone(data["signal"]["confidence"])


if __name__ == "__main__":
    unittest.main()
