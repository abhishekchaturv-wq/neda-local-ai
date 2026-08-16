import unittest
from paper_risk_manager import (
    BuyerRiskManager, EntryRequest, PositionRisk, RiskAction, RiskConfig, RiskState
)


class TestBuyerRiskManager(unittest.TestCase):
    def setUp(self):
        self.rm = BuyerRiskManager(RiskConfig(starting_capital=100000))

    def test_allows_normal_entry(self):
        r = self.rm.evaluate_entry(EntryRequest(1500, 14), RiskState())
        self.assertEqual(r.action, RiskAction.ALLOW)

    def test_per_trade_limit(self):
        r = self.rm.evaluate_entry(EntryRequest(2500, 14), RiskState())
        self.assertEqual(r.reason, "PER_TRADE_PREMIUM_LIMIT_EXCEEDED")

    def test_daily_loss_limit(self):
        r = self.rm.evaluate_entry(EntryRequest(1000, 14),
                                   RiskState(realized_pnl_today=-3000))
        self.assertEqual(r.reason, "DAILY_LOSS_LIMIT_REACHED")

    def test_consecutive_loss_limit(self):
        r = self.rm.evaluate_entry(EntryRequest(1000, 14),
                                   RiskState(consecutive_losses=3))
        self.assertEqual(r.reason, "CONSECUTIVE_LOSS_LIMIT_REACHED")

    def test_position_limit(self):
        r = self.rm.evaluate_entry(EntryRequest(1000, 14),
                                   RiskState(open_positions=3))
        self.assertEqual(r.reason, "MAX_OPEN_POSITIONS_REACHED")

    def test_total_premium_limit(self):
        r = self.rm.evaluate_entry(EntryRequest(3000, 14),
                                   RiskState(open_premium=6000))
        self.assertEqual(r.reason, "TOTAL_PREMIUM_LIMIT_EXCEEDED")

    def test_expiry_protection(self):
        r = self.rm.evaluate_position(PositionRisk(1000, 900, 1))
        self.assertEqual(r.action, RiskAction.EXIT)
        self.assertEqual(r.reason, "EXPIRY_PROTECTION")

    def test_stop_loss(self):
        r = self.rm.evaluate_position(PositionRisk(1000, 600, 10))
        self.assertEqual(r.reason, "STOP_LOSS")

    def test_take_profit(self):
        r = self.rm.evaluate_position(PositionRisk(1000, 1800, 10))
        self.assertEqual(r.reason, "TAKE_PROFIT")

    def test_short_option_is_not_a_risk_action(self):
        self.assertFalse(hasattr(RiskAction, "SELL_TO_OPEN"))


if __name__ == "__main__":
    unittest.main()
