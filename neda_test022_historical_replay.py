"""
TEST-022 — Historical BTC Research & Replay Engine

Design goals:
- Replay only timestamped, source-labelled historical observations.
- Never synthesize missing market data.
- Record provenance for every source file/HTTP response.
- Detect timestamp/order/duplicate gaps.
- Refuse replay when provenance is absent or data is marked synthetic.
- Keep the replay deterministic.
- Separate research and validation periods.
- Produce an audit trail suitable for later paper-trading comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
import csv
import hashlib
import json
import urllib.request

UTC = timezone.utc


class ProvenanceError(ValueError):
    pass


class ReplayIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class DataProvenance:
    source_name: str
    source_url: str
    retrieved_at: str
    raw_sha256: str
    dataset_sha256: str
    record_count: int
    synthetic: bool = False


@dataclass(frozen=True)
class BTCBar:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class AuditRecord:
    timestamp: int
    source_name: str
    source_url: str
    dataset_sha256: str
    raw_sha256: str
    sequence: int


@dataclass
class ReplayResult:
    dataset_sha256: str
    source_name: str
    records_replayed: int
    research_records: int
    validation_records: int
    audit_records: list[AuditRecord]
    deterministic_hash: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_number(value: float) -> float:
    """Normalize parsed CSV values so 100 and 100.0 hash identically."""
    return float(value)


def canonical_dataset_hash(rows: Sequence[BTCBar]) -> str:
    # Canonicalize all numeric OHLCV values as floats.  CSV parsing produces
    # floats, while unit-test fixtures may contain integer literals.  Without
    # this normalization the same dataset could hash differently depending on
    # whether it came from a CSV file or an in-memory fixture.
    payload = [
        {
            "timestamp": int(r.timestamp),
            "open": _canonical_number(r.open),
            "high": _canonical_number(r.high),
            "low": _canonical_number(r.low),
            "close": _canonical_number(r.close),
            "volume": _canonical_number(r.volume),
        }
        for r in rows
    ]
    return sha256_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )


def validate_provenance(p: DataProvenance) -> None:
    if not p.source_name or not p.source_url:
        raise ProvenanceError("SOURCE_PROVENANCE_REQUIRED")
    if not p.raw_sha256 or not p.dataset_sha256:
        raise ProvenanceError("SOURCE_HASH_REQUIRED")
    if p.synthetic:
        raise ProvenanceError("SYNTHETIC_DATA_REJECTED")


def validate_bars(rows: Sequence[BTCBar]) -> None:
    if not rows:
        raise ReplayIntegrityError("EMPTY_DATASET")
    previous = None
    seen = set()
    for row in rows:
        if row.timestamp in seen:
            raise ReplayIntegrityError("DUPLICATE_TIMESTAMP")
        seen.add(row.timestamp)
        if previous is not None and row.timestamp <= previous:
            raise ReplayIntegrityError("NON_MONOTONIC_TIMESTAMP")
        if min(row.open, row.high, row.low, row.close, row.volume) < 0:
            raise ReplayIntegrityError("NEGATIVE_MARKET_VALUE")
        if row.high < max(row.open, row.close, row.low):
            raise ReplayIntegrityError("INVALID_HIGH")
        if row.low > min(row.open, row.close, row.high):
            raise ReplayIntegrityError("INVALID_LOW")
        previous = row.timestamp


def load_csv(path: str | Path, provenance: DataProvenance) -> tuple[list[BTCBar], DataProvenance]:
    raw = Path(path).read_bytes()
    if sha256_bytes(raw) != provenance.raw_sha256:
        raise ProvenanceError("RAW_FILE_HASH_MISMATCH")
    validate_provenance(provenance)

    rows: list[BTCBar] = []
    text = raw.decode("utf-8")
    reader = csv.DictReader(text.splitlines())
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise ReplayIntegrityError("REQUIRED_COLUMNS_MISSING")

    for item in reader:
        rows.append(
            BTCBar(
                timestamp=int(item["timestamp"]),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item["volume"]),
            )
        )

    validate_bars(rows)
    dataset_hash = canonical_dataset_hash(rows)
    if dataset_hash != provenance.dataset_sha256:
        raise ProvenanceError("DATASET_HASH_MISMATCH")
    if provenance.record_count != len(rows):
        raise ProvenanceError("RECORD_COUNT_MISMATCH")
    return rows, provenance


def fetch_binance_btc_klines(
    start_ms: int,
    end_ms: int,
    interval: str = "1h",
    limit: int = 1000,
) -> tuple[bytes, DataProvenance]:
    """
    Fetch public BTCUSDT spot klines from Binance.

    The raw response is hashed before parsing. No fixtures, generated prices,
    or cached demo data are used as a fallback.
    """
    url = (
        "https://api.binance.com/api/v3/klines"
        f"?symbol=BTCUSDT&interval={interval}&startTime={start_ms}"
        f"&endTime={end_ms}&limit={limit}"
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "NEDA-TEST022/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read()
    raw_hash = sha256_bytes(raw)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ProvenanceError("LIVE_SOURCE_NON_JSON_RESPONSE") from exc

    if not isinstance(payload, list) or not payload:
        raise ProvenanceError("LIVE_SOURCE_EMPTY_OR_INVALID")

    lines = ["timestamp,open,high,low,close,volume"]
    dataset_rows = []
    for k in payload:
        lines.append(f"{int(k[0])},{k[1]},{k[2]},{k[3]},{k[4]},{k[5]}")
        dataset_rows.append(
            BTCBar(
                timestamp=int(k[0]),
                open=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=float(k[5]),
            )
        )

    csv_bytes = ("\n".join(lines) + "\n").encode()
    validate_bars(dataset_rows)

    provenance = DataProvenance(
        source_name="Binance Public BTCUSDT Spot Klines",
        source_url=url,
        retrieved_at=datetime.now(UTC).isoformat(),
        raw_sha256=raw_hash,
        dataset_sha256=canonical_dataset_hash(dataset_rows),
        record_count=len(dataset_rows),
        synthetic=False,
    )
    return csv_bytes, provenance


def split_walk_forward(
    rows: Sequence[BTCBar],
    research_end_timestamp: int,
    validation_end_timestamp: int | None = None,
) -> tuple[list[BTCBar], list[BTCBar]]:
    research = [r for r in rows if r.timestamp <= research_end_timestamp]
    validation = [
        r for r in rows
        if r.timestamp > research_end_timestamp
        and (validation_end_timestamp is None or r.timestamp <= validation_end_timestamp)
    ]
    if not research or not validation:
        raise ReplayIntegrityError("RESEARCH_VALIDATION_SPLIT_INVALID")
    return research, validation


def replay(
    rows: Sequence[BTCBar],
    provenance: DataProvenance,
    research_end_timestamp: int,
    validation_end_timestamp: int | None = None,
) -> ReplayResult:
    validate_provenance(provenance)
    validate_bars(rows)
    dataset_hash = canonical_dataset_hash(rows)
    if dataset_hash != provenance.dataset_sha256:
        raise ProvenanceError("REPLAY_DATASET_HASH_MISMATCH")

    research, validation = split_walk_forward(
        rows, research_end_timestamp, validation_end_timestamp
    )

    audit = [
        AuditRecord(
            timestamp=row.timestamp,
            source_name=provenance.source_name,
            source_url=provenance.source_url,
            dataset_sha256=dataset_hash,
            raw_sha256=provenance.raw_sha256,
            sequence=i,
        )
        for i, row in enumerate(rows)
    ]

    deterministic_payload = {
        "dataset_sha256": dataset_hash,
        "records": [asdict(r) for r in audit],
    }
    deterministic_hash = sha256_bytes(
        json.dumps(
            deterministic_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )

    return ReplayResult(
        dataset_sha256=dataset_hash,
        source_name=provenance.source_name,
        records_replayed=len(rows),
        research_records=len(research),
        validation_records=len(validation),
        audit_records=audit,
        deterministic_hash=deterministic_hash,
    )


def write_audit(path: str | Path, result: ReplayResult) -> None:
    payload = asdict(result)
    Path(path).write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
