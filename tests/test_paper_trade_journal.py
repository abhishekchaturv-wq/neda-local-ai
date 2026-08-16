import unittest
import json
from paper_trade_journal import PaperTradeJournal, TradeRecord


def trade(trade_id="T1", pnl=250.0, exit_premium=1250.0):
    return TradeRecord(
        trade_id=trade_id,
        timestamp="2026-08-16T23:30:00+00:00",
        symbol="BTC",
        option_type="CALL",
        strike=120000,
        dte=14,
        entry_premium=1000,
        exit_premium=exit_premium,
        quantity=1,
        direction_score=0.82,
        spread_pct=0.04,
        volume=100,
        open_interest=500,
        signal_reason="BULLISH_CONTEXT",
        entry_reason="BULLISH_MOMENTUM_CALL_RISK_OK",
        selection_reason="ATM_NEAR_TERM_LIQUID_CONTRACT",
        risk_reason="RISK_LIMITS_PASSED",
        exit_reason="TAKE_PROFIT",
        realized_pnl=pnl,
        max_favorable_pnl=300,
        max_adverse_pnl=-100,
    )


class TestPaperTradeJournal(unittest.TestCase):
    def test_records_completed_trade(self):
        j = PaperTradeJournal()
        j.record(trade())
        self.assertEqual(len(j.completed()), 1)

    def test_duplicate_trade_id_rejected(self):
        j = PaperTradeJournal()
        j.record(trade())
        with self.assertRaises(ValueError):
            j.record(trade())

    def test_summary_win_rate_and_pnl(self):
        j = PaperTradeJournal()
        j.record(trade("W", 250))
        j.record(trade("L", -150, 850))
        s = j.summary()
        self.assertEqual(s["trades"], 2)
        self.assertEqual(s["wins"], 1)
        self.assertEqual(s["losses"], 1)
        self.assertEqual(s["win_rate"], 0.5)
        self.assertEqual(s["realized_pnl"], 100)

    def test_return_pct_is_calculated(self):
        t = trade()
        self.assertEqual(t.return_pct, 25.0)

    def test_feedback_contains_decision_and_outcome_fields(self):
        j = PaperTradeJournal()
        j.record(trade())
        row = j.feedback_rows()[0]
        for key in (
            "direction_score", "spread_pct", "dte", "signal_reason",
            "entry_reason", "selection_reason", "risk_reason",
            "exit_reason", "realized_pnl",
            "max_favorable_pnl", "max_adverse_pnl"
        ):
            self.assertIn(key, row)

    def test_entry_reason_is_distinct_from_signal_and_risk_reason(self):
        t = trade()
        self.assertEqual(t.signal_reason, "BULLISH_CONTEXT")
        self.assertEqual(t.entry_reason, "BULLISH_MOMENTUM_CALL_RISK_OK")
        self.assertEqual(t.selection_reason, "ATM_NEAR_TERM_LIQUID_CONTRACT")
        self.assertEqual(t.risk_reason, "RISK_LIMITS_PASSED")
        self.assertNotEqual(t.entry_reason, t.signal_reason)
        self.assertNotEqual(t.entry_reason, t.risk_reason)

    def test_json_export_is_serializable(self):
        j = PaperTradeJournal()
        j.record(trade())
        data = json.loads(j.export_json())
        self.assertEqual(data[0]["trade_id"], "T1")

    def test_open_trade_is_not_counted_as_completed(self):
        t = trade()
        t = TradeRecord(**{**t.__dict__, "exit_premium": None, "realized_pnl": None})
        j = PaperTradeJournal()
        j.record(t)
        self.assertEqual(j.summary()["trades"], 0)

    def test_invalid_option_type_rejected(self):
        with self.assertRaises(ValueError):
            TradeRecord(**{**trade().__dict__, "option_type": "SHORT"})

    def test_invalid_premium_rejected(self):
        with self.assertRaises(ValueError):
            TradeRecord(**{**trade().__dict__, "entry_premium": 0})

    def test_invalid_dte_rejected(self):
        with self.assertRaises(ValueError):
            TradeRecord(**{**trade().__dict__, "dte": -1})


if __name__ == "__main__":
    unittest.main()
