import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from neda_test022_historical_replay import (
    BTCBar,
    DataProvenance,
    ProvenanceError,
    ReplayIntegrityError,
    canonical_dataset_hash,
    load_csv,
    replay,
    split_walk_forward,
)


class TestHistoricalReplayAudit(unittest.TestCase):
    def setUp(self):
        self.rows = [
            BTCBar(1000, 100, 101, 99, 100.5, 10),
            BTCBar(2000, 100.5, 102, 100, 101.5, 11),
            BTCBar(3000, 101.5, 103, 101, 102.5, 12),
            BTCBar(4000, 102.5, 104, 102, 103.5, 13),
        ]

    def _csv_bytes(self):
        lines = ["timestamp,open,high,low,close,volume"]
        for r in self.rows:
            lines.append(
                f"{r.timestamp},{r.open},{r.high},{r.low},{r.close},{r.volume}"
            )
        return ("\n".join(lines) + "\n").encode()

    def _provenance(self, raw):
        return DataProvenance(
            source_name="TEST-VERIFIED-SOURCE",
            source_url="https://example.invalid/test-source",
            retrieved_at="2026-01-01T00:00:00+00:00",
            raw_sha256=hashlib.sha256(raw).hexdigest(),
            dataset_sha256=canonical_dataset_hash(self.rows),
            record_count=len(self.rows),
            synthetic=False,
        )

    def test_raw_hash_is_required(self):
        raw = self._csv_bytes()
        p = self._provenance(raw)
        p = DataProvenance(**{**p.__dict__, "raw_sha256": "bad"})
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "btc.csv"
            path.write_bytes(raw)
            with self.assertRaises(ProvenanceError):
                load_csv(path, p)

    def test_synthetic_data_is_rejected(self):
        raw = self._csv_bytes()
        p = self._provenance(raw)
        p = DataProvenance(**{**p.__dict__, "synthetic": True})
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "btc.csv"
            path.write_bytes(raw)
            with self.assertRaises(ProvenanceError):
                load_csv(path, p)

    def test_dataset_hash_and_record_count_are_verified(self):
        raw = self._csv_bytes()
        p = self._provenance(raw)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "btc.csv"
            path.write_bytes(raw)
            rows, _ = load_csv(path, p)
        self.assertEqual(len(rows), 4)
        self.assertEqual(canonical_dataset_hash(rows), p.dataset_sha256)

    def test_duplicate_timestamp_is_rejected(self):
        rows = list(self.rows)
        rows[1] = BTCBar(1000, 100, 102, 99, 101, 11)
        p = DataProvenance(
            "SOURCE", "https://example.invalid", "now",
            "raw", canonical_dataset_hash(rows), len(rows), False
        )
        with self.assertRaises(ReplayIntegrityError):
            replay(rows, p, 2000)

    def test_non_monotonic_timestamp_is_rejected(self):
        rows = [self.rows[0], self.rows[2], self.rows[1], self.rows[3]]
        p = DataProvenance(
            "SOURCE", "https://example.invalid", "now",
            "raw", canonical_dataset_hash(rows), len(rows), False
        )
        with self.assertRaises(ReplayIntegrityError):
            replay(rows, p, 2000)

    def test_future_data_is_not_in_research_set(self):
        research, validation = split_walk_forward(self.rows, 2000)
        self.assertEqual([r.timestamp for r in research], [1000, 2000])
        self.assertEqual([r.timestamp for r in validation], [3000, 4000])

    def test_replay_emits_per_record_provenance(self):
        raw = self._csv_bytes()
        p = self._provenance(raw)
        result = replay(self.rows, p, 2000)
        self.assertEqual(result.records_replayed, 4)
        self.assertEqual(len(result.audit_records), 4)
        for i, audit in enumerate(result.audit_records):
            self.assertEqual(audit.sequence, i)
            self.assertEqual(audit.source_name, p.source_name)
            self.assertEqual(audit.source_url, p.source_url)
            self.assertEqual(audit.dataset_sha256, p.dataset_sha256)
            self.assertEqual(audit.raw_sha256, p.raw_sha256)

    def test_replay_is_deterministic(self):
        raw = self._csv_bytes()
        p = self._provenance(raw)
        a = replay(self.rows, p, 2000)
        b = replay(self.rows, p, 2000)
        self.assertEqual(a.deterministic_hash, b.deterministic_hash)


if __name__ == "__main__":
    unittest.main()
