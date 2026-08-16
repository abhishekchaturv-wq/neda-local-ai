import unittest
from datetime import date

from options_engine import OptionContract, OptionQuote, OptionSnapshot, OptionType, AssetClass
from btc_options_buyer_strategy import (
    BTCOptionsBuyerStrategy, BuyerStrategyContext, StrategyAction
)


def snap(symbol, strike, option_type, bid=100, ask=102, volume=10, oi=100):
    c = OptionContract(symbol, AssetClass.CRYPTO, date(2026, 8, 28), strike, option_type)
    return OptionSnapshot(c, 100000, OptionQuote(
        bid=bid, ask=ask, volume=volume, open_interest=oi
    ))


class TestBTCOptionsBuyerStrategy(unittest.TestCase):
    def setUp(self):
        self.engine = BTCOptionsBuyerStrategy()
        self.as_of = date(2026, 8, 16)

    def test_bullish_context_selects_call(self):
        result = self.engine.evaluate(
            [
                snap("C-BTC-100000-280826", 100000, OptionType.CALL),
                snap("P-BTC-100000-280826", 100000, OptionType.PUT),
            ],
            BuyerStrategyContext(0.8, 0.7),
            self.as_of,
        )
        self.assertEqual(result.action, StrategyAction.BUY)
        self.assertEqual(result.candidate.option_type, OptionType.CALL)

    def test_bearish_context_selects_put(self):
        result = self.engine.evaluate(
            [
                snap("C-BTC-100000-280826", 100000, OptionType.CALL),
                snap("P-BTC-100000-280826", 100000, OptionType.PUT),
            ],
            BuyerStrategyContext(-0.8, -0.7),
            self.as_of,
        )
        self.assertEqual(result.action, StrategyAction.BUY)
        self.assertEqual(result.candidate.option_type, OptionType.PUT)

    def test_weak_direction_is_no_trade(self):
        result = self.engine.evaluate(
            [snap("C-BTC-100000-280826", 100000, OptionType.CALL)],
            BuyerStrategyContext(0.2, 0.1),
            self.as_of,
        )
        self.assertEqual(result.action, StrategyAction.NO_TRADE)

    def test_wide_spread_is_rejected(self):
        result = self.engine.evaluate(
            [snap("C-BTC-100000-280826", 100000, OptionType.CALL, 80, 100)],
            BuyerStrategyContext(0.8, 0.7),
            self.as_of,
        )
        self.assertEqual(result.action, StrategyAction.NO_TRADE)

    def test_deep_otm_is_rejected(self):
        result = self.engine.evaluate(
            [snap("C-BTC-106000-280826", 106000, OptionType.CALL)],
            BuyerStrategyContext(0.8, 0.7),
            self.as_of,
        )
        self.assertEqual(result.action, StrategyAction.NO_TRADE)

    def test_low_liquidity_is_rejected(self):
        result = self.engine.evaluate(
            [snap("C-BTC-100000-280826", 100000, OptionType.CALL, volume=0, oi=0)],
            BuyerStrategyContext(0.8, 0.7),
            self.as_of,
        )
        self.assertEqual(result.action, StrategyAction.NO_TRADE)


if __name__ == "__main__":
    unittest.main()
