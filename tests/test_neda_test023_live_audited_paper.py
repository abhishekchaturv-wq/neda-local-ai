import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from neda_test023_live_audited_paper import (
    LiveBTCObservation,
    LiveDataError,
    PaperDecisionAudit,
    PaperOnlyViolation,
    append_audit,
    paper_action,
    require_real_observation,
    run_single_audited_observation,
    save_session_state,
    load_session_state,
)


class TestFinalLiveAuditedPaperTrading(unittest.TestCase):
    def observation(self, **kw):
        values = dict(
            observed_at="2026-08-17T00:00:00+00:00",
            exchange_timestamp_ms=0,
            source="Verified Public BTC Source",
            source_url="https://example.invalid/btc",
            symbol="BTCUSDT",
            price=100000.0,
            raw_sha256="abc123",
            synthetic=False,
        )
        values.update(kw)
        return LiveBTCObservation(**values)

    def test_synthetic_observation_rejected(self):
        with self.assertRaises(LiveDataError):
            require_real_observation(self.observation(synthetic=True))

    def test_missing_provenance_rejected(self):
        with self.assertRaises(LiveDataError):
            require_real_observation(self.observation(source_url=""))

    def test_invalid_price_rejected(self):
        with self.assertRaises(LiveDataError):
            require_real_observation(self.observation(price=0))

    def test_paper_actions_are_closed_set(self):
        for action in ("BUY", "SELL_TO_CLOSE", "HOLD", "NO_TRADE"):
            self.assertEqual(paper_action(action), action)
        with self.assertRaises(PaperOnlyViolation):
            paper_action("BROKER_BUY")

    def test_audit_contains_real_source_and_hash(self):
        obs = self.observation()
        audit = PaperDecisionAudit(
            observation=obs,
            signal_reason="test signal",
            entry_reason="test entry",
            selection_reason="test selection",
            risk_reason="test risk",
            action="NO_TRADE",
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "audit.jsonl"
            append_audit(p, audit)
            record = json.loads(p.read_text())
        self.assertEqual(record["observation"]["source"], obs.source)
        self.assertEqual(record["observation"]["source_url"], obs.source_url)
        self.assertEqual(record["observation"]["raw_sha256"], obs.raw_sha256)
        self.assertFalse(record["observation"]["synthetic"])

    def test_state_round_trip_is_paper_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state.json"
            save_session_state(p, {"position": None})
            state = load_session_state(p)
        self.assertTrue(state["paper_only"])

    @patch("neda_test023_live_audited_paper.fetch_real_btc_price")
    def test_live_observation_is_audited(self, fetch):
        fetch.return_value = self.observation()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "audit.jsonl"
            result = run_single_audited_observation(p)
            self.assertEqual(result.action, "NO_TRADE")
            self.assertEqual(result.observation.source, "Verified Public BTC Source")
            self.assertTrue(p.exists())

    @patch("neda_test023_live_audited_paper.urlopen")
    def test_live_source_has_no_synthetic_fallback(self, urlopen):
        urlopen.side_effect = OSError("network down")
        from neda_test023_live_audited_paper import fetch_real_btc_price
        with self.assertRaises(LiveDataError):
            fetch_real_btc_price()


if __name__ == "__main__":
    unittest.main()
