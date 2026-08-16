import unittest
from datetime import date
from options_engine import OptionContract, OptionQuote, OptionSnapshot, OptionType, AssetClass
from btc_options_buyer_strategy import BTCOptionsBuyerStrategy, BuyerStrategyContext, StrategyAction

def snap(symbol, strike, option_type, expiry=date(2026,8,28), bid=100, ask=102, volume=10, oi=100):
    c = OptionContract(symbol, AssetClass.CRYPTO, expiry, strike, option_type)
    return OptionSnapshot(c, 100000, OptionQuote(bid=bid, ask=ask, volume=volume, open_interest=oi))

class TestBTCOptionsBuyerStrategy(unittest.TestCase):
    def setUp(self):
        self.engine = BTCOptionsBuyerStrategy()
        self.as_of = date(2026,8,16)

    def test_bullish_context_selects_call(self):
        r=self.engine.evaluate([snap("BTC-C-100000",100000,OptionType.CALL),
                                snap("BTC-P-100000",100000,OptionType.PUT)],
                               BuyerStrategyContext(.8,.7),self.as_of)
        self.assertEqual(r.action,StrategyAction.BUY)
        self.assertEqual(r.candidate.option_type,OptionType.CALL)

    def test_bearish_context_selects_put(self):
        r=self.engine.evaluate([snap("BTC-C-100000",100000,OptionType.CALL),
                                snap("BTC-P-100000",100000,OptionType.PUT)],
                               BuyerStrategyContext(-.8,-.7),self.as_of)
        self.assertEqual(r.action,StrategyAction.BUY)
        self.assertEqual(r.candidate.option_type,OptionType.PUT)

    def test_weak_direction_is_no_trade(self):
        r=self.engine.evaluate([snap("BTC-C-100000",100000,OptionType.CALL)],
                               BuyerStrategyContext(.2,.1),self.as_of)
        self.assertEqual(r.action,StrategyAction.NO_TRADE)

    def test_wide_spread_is_rejected(self):
        r=self.engine.evaluate([snap("BTC-C-100000",100000,OptionType.CALL,bid=80,ask=100)],
                               BuyerStrategyContext(.8,.7),self.as_of)
        self.assertEqual(r.action,StrategyAction.NO_TRADE)

    def test_deep_otm_is_rejected(self):
        r=self.engine.evaluate([snap("BTC-C-106000",106000,OptionType.CALL)],
                               BuyerStrategyContext(.8,.7),self.as_of)
        self.assertEqual(r.action,StrategyAction.NO_TRADE)

    def test_low_liquidity_is_rejected(self):
        r=self.engine.evaluate([snap("BTC-C-100000",100000,OptionType.CALL,volume=0,oi=0)],
                               BuyerStrategyContext(.8,.7),self.as_of)
        self.assertEqual(r.action,StrategyAction.NO_TRADE)

if __name__=="__main__":
    unittest.main()
