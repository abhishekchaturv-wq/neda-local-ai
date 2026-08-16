import unittest
from datetime import date

from options_engine import (
    AssetClass,
    Greeks,
    OptionContract,
    OptionQuote,
    OptionSnapshot,
    OptionType,
)
from options_chain import analyze_chain


def snap(strike, option_type, oi, change, volume):
    contract = OptionContract(
        symbol="NIFTY",
        asset_class=AssetClass.INDEX,
        expiry=date(2026, 9, 24),
        strike=strike,
        option_type=option_type,
    )
    quote = OptionQuote(
        bid=10.0,
        ask=12.0,
        volume=volume,
        open_interest=oi,
        change_in_open_interest=change,
    )
    return OptionSnapshot(
        contract=contract,
        underlying_price=25000,
        quote=quote,
        greeks=Greeks(),
    )


class OptionsChainV1Tests(unittest.TestCase):
    def test_totals_and_pcr(self):
        result = analyze_chain([
            snap(24900, OptionType.CALL, 100, 10, 50),
            snap(24900, OptionType.PUT, 200, 20, 100),
            snap(25000, OptionType.CALL, 300, 30, 150),
            snap(25000, OptionType.PUT, 600, 60, 300),
        ])
        self.assertEqual(result.call_oi, 400)
        self.assertEqual(result.put_oi, 800)
        self.assertEqual(result.call_change_oi, 40)
        self.assertEqual(result.put_change_oi, 80)
        self.assertEqual(result.call_volume, 200)
        self.assertEqual(result.put_volume, 400)
        self.assertEqual(result.pcr_oi, 2.0)
        self.assertEqual(result.pcr_volume, 2.0)

    def test_zero_denominator_returns_none(self):
        result = analyze_chain([
            snap(25000, OptionType.PUT, 100, 0, 100),
        ])
        self.assertIsNone(result.pcr_oi)
        self.assertIsNone(result.pcr_volume)

    def test_max_pain(self):
        result = analyze_chain([
            snap(24000, OptionType.CALL, 100, 0, 0),
            snap(25000, OptionType.CALL, 200, 0, 0),
            snap(25000, OptionType.PUT, 300, 0, 0),
            snap(26000, OptionType.PUT, 100, 0, 0),
        ])
        self.assertEqual(result.max_pain, 25000)

    def test_empty_chain(self):
        result = analyze_chain([])
        self.assertEqual(result.call_oi, 0)
        self.assertEqual(result.put_oi, 0)
        self.assertIsNone(result.pcr_oi)
        self.assertIsNone(result.pcr_volume)
        self.assertIsNone(result.max_pain)
        self.assertEqual(result.strikes, ())

    def test_strike_summaries(self):
        result = analyze_chain([
            snap(25000, OptionType.CALL, 100, 5, 20),
            snap(25000, OptionType.PUT, 200, 10, 40),
            snap(25100, OptionType.CALL, 300, 15, 60),
        ])
        self.assertEqual(len(result.strikes), 2)
        self.assertEqual(result.strikes[0].strike, 25000)
        self.assertEqual(result.strikes[0].call_oi, 100)
        self.assertEqual(result.strikes[0].put_oi, 200)
        self.assertEqual(result.strikes[0].call_change_oi, 5)
        self.assertEqual(result.strikes[0].put_change_oi, 10)
        self.assertEqual(result.strikes[1].call_volume, 60)

    def test_invalid_oi_is_rejected(self):
        # OptionQuote validates the raw quote before OptionSnapshot is built.
        with self.assertRaises(ValueError):
            OptionQuote(open_interest=-1)


if __name__ == "__main__":
    unittest.main()
