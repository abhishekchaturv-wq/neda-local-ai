import unittest
from datetime import date

from options_engine import AssetClass, OptionContract, OptionType, make_contract


class CryptoAssetClassTests(unittest.TestCase):
    def test_crypto_asset_class_exists(self):
        self.assertEqual(AssetClass.CRYPTO.value, "CRYPTO")

    def test_btc_call_contract(self):
        contract = OptionContract(
            "BTC", AssetClass.CRYPTO, date(2026, 8, 28), 118000, OptionType.CALL
        )
        self.assertEqual(contract.symbol, "BTC")
        self.assertEqual(contract.asset_class, AssetClass.CRYPTO)

    def test_make_contract_accepts_crypto_string(self):
        contract = make_contract(
            "btc", "crypto", date(2026, 8, 28), 120000, "put"
        )
        self.assertEqual(contract.symbol, "BTC")
        self.assertEqual(contract.asset_class, AssetClass.CRYPTO)
        self.assertEqual(contract.option_type, OptionType.PUT)


if __name__ == "__main__":
    unittest.main()
