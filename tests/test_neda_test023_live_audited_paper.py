import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from neda_test023_live_audited_paper import (
    DeltaLiveObservation,
    LiveDataError,
    PaperDecisionAudit,
    PaperOnlyViolation,
    append_audit,
    fetch_real_delta_btc_options,
    live_data_boundary_audit,
    paper_action,
    require_real_observation,
    save_session_state,
)


class TestFinalLiveAuditedPaperTrading(unittest.TestCase):
    def observation(self, **kw):
        values = dict(
            observed_at="2026-08-17T00:00:00+00:00",
            source="DeltaExchangeIndiaPublicREST",
            source_url="https://api.india.delta.exchange/v2/tickers",
            raw_sha256="abc123",
            symbol="BTC",
            underlying_price=100000.0,
            option_count=10,
            synthetic=False,
        )
        values.update(kw)
        return DeltaLiveObservation(**values)

    def test_synthetic_observation_rejected(self):
        with self.assertRaises(LiveDataError):
            require_real_observation(self.observation(synthetic=True))

    def test_missing_provenance_rejected(self):
        with self.assertRaises(LiveDataError):
            require_real_observation(self.observation(source_url=""))

    def test_invalid_delta_observation_rejected(self):
        with self.assertRaises(LiveDataError):
            require_real_observation(self.observation(option_count=0))

    def test_paper_actions_are_closed_set(self):
        for action in ("BUY", "SELL_TO_CLOSE", "HOLD", "NO_TRADE"):
            self.assertEqual(paper_action(action), action)
        with self.assertRaises(PaperOnlyViolation):
            paper_action("BROKER_BUY")

    def test_audit_contains_delta_source_and_hash(self):
        obs = self.observation()
        audit = PaperDecisionAudit(
            observation=obs,
            signal_reason="signal",
            entry_reason="entry",
            selection_reason="selection",
            risk_reason="risk",
            action="NO_TRADE",
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "audit.jsonl"
            append_audit(p, audit)
            record = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(record["observation"]["source"], "DeltaExchangeIndiaPublicREST")
        self.assertIn("api.india.delta.exchange", record["observation"]["source_url"])
        self.assertEqual(record["observation"]["raw_sha256"], "abc123")
        self.assertFalse(record["observation"]["synthetic"])

    def test_state_is_paper_only(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "state.json"
            save_session_state(p, {"position": None})
            state = json.loads(p.read_text(encoding="utf-8"))
        self.assertTrue(state["paper_only"])

    @patch("neda_test023_live_audited_paper.urlopen")
    def test_delta_response_is_audited_without_fallback(self, urlopen):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                return (
                    b'{"success":true,"result":['
                    b'{"symbol":"C-BTC-100000-300826",'
                    b'"contract_type":"call_options",'
                    b'"spot_price":"100000",'
                    b'"quotes":{"best_bid":"100","best_ask":"110"}}]}'
                )
        urlopen.return_value = Response()
        obs = fetch_real_delta_btc_options()
        self.assertEqual(obs.source, "DeltaExchangeIndiaPublicREST")
        self.assertEqual(obs.symbol, "BTC")
        self.assertEqual(obs.option_count, 1)
        self.assertNotEqual(obs.raw_sha256, "")

    @patch("neda_test023_live_audited_paper.urlopen")
    def test_network_failure_has_no_synthetic_fallback(self, urlopen):
        urlopen.side_effect = OSError("network down")
        with self.assertRaises(LiveDataError):
            fetch_real_delta_btc_options()

    @patch("neda_test023_live_audited_paper.fetch_real_delta_btc_options")
    def test_live_boundary_produces_audited_no_trade(self, fetch):
        fetch.return_value = self.observation()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "audit.jsonl"
            result = live_data_boundary_audit(p)
            self.assertEqual(result.action, "NO_TRADE")
            self.assertEqual(
                result.observation.source,
                "DeltaExchangeIndiaPublicREST",
            )
            self.assertTrue(p.exists())


if __name__ == "__main__":
    unittest.main()
