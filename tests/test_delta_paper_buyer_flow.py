import unittest
from datetime import date
from delta_market_data import DeltaPublicClient, DeltaBTCOptionProvider
from paper_trading import (
    BuyerOnlyPaperExecutionAdapter,
    PaperOrderStatus,
    PaperSide,
)

class R:
    def __init__(self, payload):
        import json
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.payload

class TestDeltaPaperBuyerFlow(unittest.TestCase):
    def _provider(self):
        def opener(req, timeout=0):
            return R({
                "success": True,
                "result": [{
                    "symbol": "C-BTC-100000-280826",
                    "contract_type": "call_options",
                    "strike_price": "100000",
                    "spot_price": "118500",
                    "close": "2200",
                    "oi": "120",
                    "volume": 50,
                    "expiry_date": "28-08-2026",
                    "quotes": {
                        "best_bid": "2190",
                        "best_ask": "2210",
                        "bid_iv": "0.55"
                    }
                }]
            })
        return DeltaBTCOptionProvider(DeltaPublicClient(opener=opener))

    def test_live_delta_snapshot_feeds_paper_buy(self):
        snapshot = self._provider().snapshot(date(2026, 8, 28))
        quote = snapshot.options[0].quote
        engine = BuyerOnlyPaperExecutionAdapter()
        order = engine.submit(
            snapshot.options[0].contract.symbol,
            PaperSide.BUY,
            1,
            quote.bid,
            quote.ask,
        )
        self.assertEqual(order.status, PaperOrderStatus.FILLED)
        self.assertEqual(order.fill_price, quote.ask)
        self.assertEqual(engine.positions[order.symbol].quantity, 1)

    def test_sell_to_open_is_rejected(self):
        snapshot = self._provider().snapshot(date(2026, 8, 28))
        quote = snapshot.options[0].quote
        engine = BuyerOnlyPaperExecutionAdapter()
        order = engine.submit(
            snapshot.options[0].contract.symbol,
            PaperSide.SELL,
            1,
            quote.bid,
            quote.ask,
        )
        self.assertEqual(order.status, PaperOrderStatus.REJECTED)
        self.assertEqual(
            order.reason,
            "OPTIONS_BUYER_POLICY_SELL_TO_OPEN_FORBIDDEN",
        )

    def test_sell_to_close_is_allowed(self):
        snapshot = self._provider().snapshot(date(2026, 8, 28))
        quote = snapshot.options[0].quote
        engine = BuyerOnlyPaperExecutionAdapter()
        symbol = snapshot.options[0].contract.symbol
        engine.submit(symbol, PaperSide.BUY, 1, quote.bid, quote.ask)
        order = engine.submit(symbol, PaperSide.SELL, 1, 2240, 2250)
        self.assertEqual(order.status, PaperOrderStatus.FILLED)
        self.assertEqual(engine.positions[symbol].quantity, 0)
        self.assertEqual(engine.positions[symbol].realized_pnl, 30)

    def test_no_live_broker_execution(self):
        engine = BuyerOnlyPaperExecutionAdapter()
        self.assertEqual(engine.MODE, "PAPER_BUYER_ONLY")
        self.assertEqual(engine.broker_call_count(), 0)

if __name__ == "__main__":
    unittest.main()
