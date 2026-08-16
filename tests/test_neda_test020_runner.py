import unittest
from datetime import date, timedelta
from unittest.mock import Mock

from btc_options_buyer_strategy import BuyerStrategyContext
from delta_market_data import DeltaMarketSnapshot
from options_engine import AssetClass, OptionContract, OptionQuote, OptionSnapshot, OptionType
from paper_risk_manager import RiskConfig
from paper_trading import PaperOrderStatus
from paper_trade_journal import PaperTradeJournal
from neda_test020_runner import EndToEndPaperTradingRunner


class FakeProvider:
    def __init__(self):
        expiry = date.today() + timedelta(days=14)
        contract = OptionContract("BTC", AssetClass.CRYPTO, expiry, 100000.0, OptionType.CALL)
        quote = OptionQuote(
            bid=100.0, ask=105.0, last=102.0, volume=100, open_interest=200
        )
        self.snapshot_data = DeltaMarketSnapshot(
            "BTC", expiry, 100000.0,
            (OptionSnapshot(contract, 100000.0, quote),),
            123.0, "DeltaExchangeIndiaPublicREST", True
        )

    def snapshot(self):
        return self.snapshot_data


class TestEndToEndPaperRunner(unittest.TestCase):
    def make_runner(self):
        return EndToEndPaperTradingRunner(
            provider=FakeProvider(),
            journal=PaperTradeJournal(),
        )

    def test_end_to_end_buy_then_exit_and_journal(self):
        runner = self.make_runner()
        result = runner.run_once(BuyerStrategyContext(0.9, 0.8), quantity=1)
        self.assertEqual(result.action, "BUY")
        self.assertIsNotNone(result.trade_id)
        self.assertEqual(runner.broker_call_count(), 0)
        self.assertEqual(result.entry_reason, "QUALIFIED_BUYER_CANDIDATE")
        self.assertTrue(result.selection_reason)
        self.assertTrue(result.risk_reason)

        exit_result = runner.mark_and_maybe_exit(110.0, 10)
        self.assertEqual(exit_result.action, "HOLD")
        self.assertEqual(len(runner.journal.completed()), 0)

        exit_result = runner.mark_and_maybe_exit(200.0, 1)
        self.assertEqual(exit_result.action, "SELL_TO_CLOSE")
        self.assertEqual(len(runner.journal.completed()), 1)
        row = runner.journal.feedback_rows()[0]
        self.assertEqual(row["entry_reason"], "QUALIFIED_BUYER_CANDIDATE")
        self.assertEqual(row["exit_reason"], "EXPIRY_PROTECTION")
        self.assertGreater(row["realized_pnl"], 0)

    def test_weak_signal_is_no_trade(self):
        runner = self.make_runner()
        result = runner.run_once(BuyerStrategyContext(0.1, 0.1))
        self.assertEqual(result.action, "NO_TRADE")
        self.assertEqual(result.decision_reason, "DIRECTIONAL_SIGNAL_TOO_WEAK")
        self.assertEqual(runner.broker_call_count(), 0)

    def test_kill_switch_style_risk_rejection(self):
        runner = self.make_runner()
        state = __import__("paper_risk_manager").RiskState(
            realized_pnl_today=-3000.0
        )
        result = runner.run_once(BuyerStrategyContext(0.9, 0.8), risk_state=state)
        self.assertEqual(result.action, "NO_TRADE")
        self.assertEqual(result.risk_reason, "DAILY_LOSS_LIMIT_REACHED")
        self.assertEqual(runner.broker_call_count(), 0)


if __name__ == "__main__":
    unittest.main()
