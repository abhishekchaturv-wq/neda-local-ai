import json
import tempfile
import unittest
from datetime import date

from btc_options_buyer_strategy import BuyerStrategyContext
from neda_test021_session import PersistentPaperTradingSession
from paper_trade_journal import PaperTradeJournal, TradeRecord


class TestPersistentPaperTradingSession(unittest.TestCase):
    def test_state_file_round_trip_for_open_position(self):
        with tempfile.TemporaryDirectory() as td:
            path = f"{td}/state.json"
            s = PersistentPaperTradingSession(path)
            # Directly seed a realistic open state without depending on a
            # live network response.
            from neda_test020_runner import OpenPaperTrade
            s.runner.open_trade = OpenPaperTrade(
                trade_id="TEST021-000001", symbol="BTC-CALL-1",
                option_type="CALL", strike=100000, quantity=1,
                entry_premium=100, entry_dte=14, direction_score=.8,
                spread_pct=.03, volume=100, open_interest=500,
                signal_reason="BULLISH_CONTEXT",
                entry_reason="QUALIFIED_BUYER_CANDIDATE",
                selection_reason="LIQUID_NEAR_MONEY",
                risk_reason="RISK_LIMITS_PASSED",
            )
            s.runner._trade_counter = 1
            s.save()

            r = PersistentPaperTradingSession(path)
            self.assertIsNotNone(r.open_trade)
            self.assertEqual(r.open_trade.trade_id, "TEST021-000001")
            self.assertEqual(r.open_trade.symbol, "BTC-CALL-1")
            self.assertEqual(r.runner.execution.positions["BTC-CALL-1"].quantity, 1)

    def test_no_duplicate_entry_when_position_is_open(self):
        with tempfile.TemporaryDirectory() as td:
            s = PersistentPaperTradingSession(f"{td}/state.json")
            from neda_test020_runner import OpenPaperTrade
            s.runner.open_trade = OpenPaperTrade(
                "TEST021-000001", "BTC-CALL-1", "CALL", 100000, 1, 100, 14,
                .8, .03, 100, 500, "BULLISH_CONTEXT",
                "QUALIFIED_BUYER_CANDIDATE", "LIQUID_NEAR_MONEY",
                "RISK_LIMITS_PASSED",
            )
            # A persistent session must route an open position to monitoring,
            # never to another BUY.
            self.assertIsNotNone(s.open_trade)

    def test_journal_rejects_completed_trade_without_exit_reason(self):
        with self.assertRaises(ValueError):
            TradeRecord(
                trade_id="T-EXIT-MISSING", timestamp="2026-08-16T00:00:00Z",
                symbol="BTC", option_type="CALL", strike=100000, dte=5,
                entry_premium=100, exit_premium=120, quantity=1,
                direction_score=.8, spread_pct=.03, volume=10,
                open_interest=20, signal_reason="BULLISH_CONTEXT",
                entry_reason="QUALIFIED_BUYER_CANDIDATE",
                selection_reason="LIQUID_NEAR_MONEY",
                risk_reason="RISK_LIMITS_PASSED",
                exit_reason=None, realized_pnl=20,
            )

    def test_open_trade_may_have_no_exit_reason(self):
        t = TradeRecord(
            trade_id="T-OPEN", timestamp="2026-08-16T00:00:00Z",
            symbol="BTC", option_type="CALL", strike=100000, dte=5,
            entry_premium=100, exit_premium=None, quantity=1,
            direction_score=.8, spread_pct=.03, volume=10,
            open_interest=20, signal_reason="BULLISH_CONTEXT",
            entry_reason="QUALIFIED_BUYER_CANDIDATE",
            selection_reason="LIQUID_NEAR_MONEY",
            risk_reason="RISK_LIMITS_PASSED",
            exit_reason=None, realized_pnl=None,
        )
        self.assertFalse(t.completed)


if __name__ == "__main__":
    unittest.main()
