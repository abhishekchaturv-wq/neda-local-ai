import unittest
from datetime import date
from options_engine import *
class OptionsEngineV1Tests(unittest.TestCase):
    def setUp(self): self.expiry=date(2026,9,24)
    def test_factory(self):
        c=make_contract(" nifty ","index",self.expiry,25000,"call"); self.assertEqual(c.symbol,"NIFTY"); self.assertIs(c.asset_class,AssetClass.INDEX); self.assertIs(c.option_type,OptionType.CALL)
    def test_call(self):
        c=OptionContract("NIFTY",AssetClass.INDEX,self.expiry,25000,OptionType.CALL); s=OptionSnapshot(c,25200,OptionQuote(bid=210,ask=220)); self.assertEqual(s.intrinsic_value,200); self.assertIs(s.moneyness,Moneyness.ITM); self.assertEqual(s.mid_price,215)
    def test_put(self):
        c=OptionContract("CRUDEOIL",AssetClass.COMMODITY,self.expiry,7000,OptionType.PUT); s=OptionSnapshot(c,6800,OptionQuote(last=230)); self.assertEqual(s.intrinsic_value,200); self.assertIs(s.moneyness,Moneyness.ITM)
    def test_atm(self):
        c=OptionContract("RELIANCE",AssetClass.STOCK,self.expiry,2500,OptionType.CALL); self.assertIs(OptionSnapshot(c,2508,OptionQuote(last=35)).moneyness,Moneyness.ATM)
    def test_bad_quote(self):
        with self.assertRaises(ValueError): OptionQuote(bid=110,ask=100)
    def test_bad_contract(self):
        with self.assertRaises(ValueError): OptionContract("NIFTY",AssetClass.INDEX,self.expiry,0,OptionType.CALL)
    def test_key(self): self.assertEqual(make_contract("banknifty","index",self.expiry,56000,"put").key,"BANKNIFTY|2026-09-24|56000|PUT")
if __name__=="__main__": unittest.main()
