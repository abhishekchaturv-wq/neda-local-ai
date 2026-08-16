import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from btc_options_buyer_strategy import BuyerStrategyContext
from neda_test022_live_paper_trading import run_session


class TestLivePaperTradingSession(unittest.TestCase):
    def test_weak_signal_is_audited_as_no_trade(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            log = Path(td) / "decisions.jsonl"
            rows = run_session(state, log, 0.10, 0.10, cycles=1)
            self.assertEqual(rows[0]["action"], "NO_TRADE")
            self.assertEqual(rows[0]["decision_reason"], "DIRECTIONAL_SIGNAL_TOO_WEAK")
            self.assertIsNone(rows[0]["entry_reason"])
            self.assertEqual(log.read_text(encoding="utf-8").count("\n"), 1)

    def test_session_is_restart_safe(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            log = Path(td) / "decisions.jsonl"

            with patch("neda_test022_live_paper_trading.PersistentPaperTradingSession.broker_call_count", return_value=0):
                rows = run_session(state, log, 0.10, 0.10, cycles=1)

            self.assertTrue(state.exists())
            payload = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 1)
            self.assertEqual(rows[0]["action"], "NO_TRADE")

    def test_invalid_context_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                run_session(Path(td) / "state.json", Path(td) / "log.jsonl", 2.0, 0.0)

    def test_broker_safety_failure_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            with patch(
                "neda_test022_live_paper_trading.PersistentPaperTradingSession.broker_call_count",
                return_value=1,
            ):
                with self.assertRaises(RuntimeError):
                    run_session(
                        Path(td) / "state.json",
                        Path(td) / "log.jsonl",
                        0.10, 0.10,
                        cycles=1,
                    )


if __name__ == "__main__":
    unittest.main()
