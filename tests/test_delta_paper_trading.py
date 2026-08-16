import json, unittest
from datetime import date
from delta_market_data import DeltaPublicClient, DeltaBTCOptionProvider
from paper_trading import PaperExecutionAdapter, PaperOrderStatus, PaperSide

class R:
    def __init__(self,p): self.p=json.dumps(p).encode()
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def read(self): return self.p

class Tests(unittest.TestCase):
    def test_delta_public_btc_option_chain(self):
        calls=[]
        def opener(req,timeout=0):
            calls.append((req.full_url,req.method))
            return R({"success":True,"result":[{
                "symbol":"C-BTC-100000-280826","contract_type":"call_options",
                "strike_price":"100000","spot_price":"118500","close":"2200",
                "oi":"120","volume":50,"expiry_date":"28-08-2026",
                "quotes":{"best_bid":"2190","best_ask":"2210","bid_iv":"0.55"}}]})
        snap=DeltaBTCOptionProvider(DeltaPublicClient(opener=opener)).snapshot(date(2026,8,28))
        self.assertEqual(snap.symbol,"BTC")
        self.assertEqual(snap.underlying_price,118500)
        self.assertEqual(snap.options[0].quote.ask,2210)
        self.assertEqual(snap.options[0].contract.asset_class.value,"CRYPTO")
        self.assertTrue(calls[0][0].startswith("https://api.india.delta.exchange/v2/tickers?"))
        self.assertEqual(calls[0][1],"GET")

    def test_paper_buy_at_ask(self):
        p=PaperExecutionAdapter()
        o=p.submit("C-BTC-100000-280826",PaperSide.BUY,2,2190,2210)
        self.assertEqual(o.status,PaperOrderStatus.FILLED)
        self.assertEqual(o.fill_price,2210)
        self.assertEqual(p.positions[o.symbol].quantity,2)

    def test_paper_sell_realizes_pnl(self):
        p=PaperExecutionAdapter()
        p.submit("C-BTC-100000-280826",PaperSide.BUY,1,2190,2210)
        p.submit("C-BTC-100000-280826",PaperSide.SELL,1,2240,2250)
        self.assertEqual(p.positions["C-BTC-100000-280826"].realized_pnl,30)

    def test_non_crossing_limit_is_not_filled(self):
        p=PaperExecutionAdapter()
        o=p.submit("C-BTC-100000-280826",PaperSide.BUY,1,2190,2210,2200)
        self.assertEqual(o.status,PaperOrderStatus.ACCEPTED)

    def test_no_live_broker_execution(self):
        p=PaperExecutionAdapter()
        self.assertEqual(p.MODE,"PAPER")
        self.assertEqual(p.broker_call_count(),0)

if __name__=="__main__": unittest.main()
