"""TEST-024 autonomous, live-audited BTC paper-trading orchestrator.

Removes TEST-022's manual trend/momentum inputs. Historical BTC data is used
to derive the TEST-017 context; the exact live Delta option response used by
the paper runner is captured and hashed for audit.

Safety:
- no synthetic/demo/cached fallback;
- live data is the same Delta public REST provider used by NEDA;
- historical data is source-labelled and hashed;
- TEST-017 strategy, TEST-018 risk, TEST-021 persistence and paper execution
  remain authoritative;
- broker call count must remain zero;
- every decision records historical + live provenance;
- this module does not silently change strategy parameters.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import ssl
import statistics
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None

from btc_options_buyer_strategy import BuyerStrategyContext
from delta_market_data import DeltaBTCOptionProvider, DeltaPublicClient
from neda_test021_session import PersistentPaperTradingSession
from neda_test022_historical_replay import BTCBar, canonical_dataset_hash, validate_bars
from paper_risk_manager import RiskState


BINANCE_URL = "https://api.binance.com/api/v3/klines"


def _tls_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_get(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "NEDA/TEST-024"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_tls_context()) as response:
        return response.read()


@dataclass(frozen=True)
class HistoricalProvenance:
    source: str
    source_url: str
    retrieved_at: str
    raw_sha256: str
    dataset_sha256: str
    record_count: int
    synthetic: bool = False


@dataclass(frozen=True)
class DerivedContext:
    trend_score: float
    momentum_score: float
    directional_score: float
    lookback_records: int
    latest_historical_close: float
    live_spot: float
    method: str


@dataclass(frozen=True)
class LiveProvenance:
    source: str
    source_url: str
    observed_at: str
    raw_sha256: str
    option_count: int
    underlying_price: float
    synthetic: bool = False


class AutonomousLiveDataError(RuntimeError):
    pass


class AuditedDeltaClient(DeltaPublicClient):
    """Capture the exact raw Delta response consumed by the provider."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_live_provenance: LiveProvenance | None = None

    def _get(self, path, params=None):
        query = "?" + urlencode(params) if params else ""
        url = self.base_url + path + query
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "NEDA/TEST-024"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout, context=_tls_context()
            ) as response:
                raw = response.read()
        except Exception as exc:
            raise AutonomousLiveDataError("REAL_DELTA_SOURCE_UNAVAILABLE") from exc

        raw_hash = _sha256(raw)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise AutonomousLiveDataError("REAL_DELTA_SOURCE_INVALID_JSON") from exc

        if payload.get("success") is False:
            raise AutonomousLiveDataError("REAL_DELTA_API_ERROR")

        rows = payload.get("result")
        if isinstance(rows, list) and rows:
            usable = [
                row for row in rows
                if str(row.get("symbol", ""))
                and (
                    str(row.get("contract_type", "")).lower()
                    in {"call_options", "put_options"}
                    or str(row.get("symbol", "")).upper().startswith(("C-", "P-"))
                )
            ]
            spot = None
            for row in usable:
                value = row.get("spot_price") or row.get("underlying_price")
                try:
                    candidate = float(value)
                except (TypeError, ValueError):
                    continue
                if candidate > 0:
                    spot = candidate
                    break
            if usable and spot is not None:
                self.last_live_provenance = LiveProvenance(
                    source="DeltaExchangeIndiaPublicREST",
                    source_url=url,
                    observed_at=datetime.now(timezone.utc).isoformat(),
                    raw_sha256=raw_hash,
                    option_count=len(usable),
                    underlying_price=spot,
                    synthetic=False,
                )
        return payload


class CachedSnapshotProvider:
    """Return one pre-audited snapshot, then delegate normally."""

    def __init__(self, provider: DeltaBTCOptionProvider):
        self.provider = provider
        self._cached = None

    def prime(self, snapshot) -> None:
        self._cached = snapshot

    def snapshot(self, expiry=None):
        if self._cached is not None:
            snapshot = self._cached
            self._cached = None
            return snapshot
        return self.provider.snapshot(expiry=expiry)


def fetch_historical_btc(
    history_days: int = 30,
    interval: str = "1h",
) -> tuple[list[BTCBar], HistoricalProvenance]:
    if history_days < 7:
        raise ValueError("history_days must be at least 7")

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - history_days * 24 * 60 * 60 * 1000
    url = (
        f"{BINANCE_URL}?symbol=BTCUSDT&interval={interval}"
        f"&startTime={start_ms}&endTime={end_ms}&limit=1000"
    )
    raw = _json_get(url)
    raw_hash = _sha256(raw)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise AutonomousLiveDataError("HISTORICAL_SOURCE_INVALID_JSON") from exc

    if not isinstance(payload, list) or not payload:
        raise AutonomousLiveDataError("HISTORICAL_SOURCE_EMPTY")

    rows = [
        BTCBar(
            timestamp=int(k[0]),
            open=float(k[1]),
            high=float(k[2]),
            low=float(k[3]),
            close=float(k[4]),
            volume=float(k[5]),
        )
        for k in payload
    ]
    validate_bars(rows)

    provenance = HistoricalProvenance(
        source="Binance Public BTCUSDT Spot Klines",
        source_url=url,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        raw_sha256=raw_hash,
        dataset_sha256=canonical_dataset_hash(rows),
        record_count=len(rows),
        synthetic=False,
    )
    return rows, provenance


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))


def derive_context(rows: list[BTCBar], live_spot: float) -> DerivedContext:
    """Derive TEST-017 trend/momentum from historical BTC + current live spot."""
    validate_bars(rows)
    if live_spot <= 0:
        raise AutonomousLiveDataError("INVALID_LIVE_BTC_SPOT")

    closes = [r.close for r in rows]
    if len(closes) < 24 * 7:
        raise AutonomousLiveDataError("INSUFFICIENT_HISTORICAL_CONTEXT")

    window_7d = closes[-24 * 7:]
    lo, hi = min(window_7d), max(window_7d)
    range_score = 0.0 if hi == lo else ((live_spot - lo) / (hi - lo)) * 2.0 - 1.0

    ret_6h = live_spot / closes[-7] - 1.0
    ret_24h = live_spot / closes[-25] - 1.0
    hourly_returns = [
        closes[i] / closes[i - 1] - 1.0
        for i in range(max(1, len(closes) - 168), len(closes))
    ]
    vol = statistics.pstdev(hourly_returns) if len(hourly_returns) > 1 else 0.0
    scale = max(vol * math.sqrt(24), 0.002)
    momentum = _clip(0.55 * (ret_6h / scale) + 0.45 * (ret_24h / scale))

    mean_30d = statistics.mean(closes[-24 * 30:]) if len(closes) >= 24 * 30 else statistics.mean(closes)
    mean_component = (live_spot / mean_30d - 1.0) / 0.10
    trend = _clip(0.65 * range_score + 0.35 * mean_component)
    directional = 0.6 * trend + 0.4 * momentum

    return DerivedContext(
        trend_score=trend,
        momentum_score=momentum,
        directional_score=directional,
        lookback_records=len(rows),
        latest_historical_close=closes[-1],
        live_spot=live_spot,
        method="7D_RANGE+30D_MEAN+6H_24H_RETURN_VOL_NORMALIZATION",
    )


def run_session(
    state_path: str | Path,
    audit_path: str | Path,
    history_days: int = 30,
    quantity: float = 1.0,
    interval_seconds: float = 60.0,
    cycles: int = 1,
) -> list[dict]:
    if cycles <= 0:
        raise ValueError("cycles must be positive")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if interval_seconds < 0:
        raise ValueError("interval_seconds must be non-negative")

    rows, historical = fetch_historical_btc(history_days=history_days)

    real_client = AuditedDeltaClient()
    real_provider = DeltaBTCOptionProvider(client=real_client)
    audited_provider = CachedSnapshotProvider(real_provider)
    session = PersistentPaperTradingSession(state_path, provider=audited_provider)

    audit_file = Path(audit_path)
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    for cycle_no in range(1, cycles + 1):
        # Fetch the live snapshot FIRST. This exact snapshot is then primed into
        # the provider consumed by PersistentPaperTradingSession.
        live_snapshot = real_provider.snapshot()
        audited_provider.prime(live_snapshot)

        live = real_client.last_live_provenance
        if live is None or live.synthetic or live.option_count <= 0:
            raise AutonomousLiveDataError("LIVE_DELTA_PROVENANCE_MISSING")

        context = derive_context(rows, live.underlying_price)

        result = session.cycle(
            context=BuyerStrategyContext(context.trend_score, context.momentum_score),
            quantity=quantity,
            risk_state=RiskState(),
            as_of=datetime.now(timezone.utc).date(),
        )

        if session.broker_call_count() != 0:
            raise RuntimeError("SAFETY FAILURE: broker call count is non-zero")

        record = {
            "test": "TEST-024",
            "cycle": cycle_no,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "action": result.action,
            "trade_id": result.trade_id,
            "symbol": result.symbol,
            "decision_reason": result.decision_reason,
            "entry_reason": result.entry_reason,
            "selection_reason": result.selection_reason,
            "risk_reason": result.risk_reason,
            "exit_reason": result.risk_reason if result.action == "SELL_TO_CLOSE" else None,
            "order_status": result.order_status,
            "fill_price": result.fill_price,
            "historical": asdict(historical),
            "derived_context": asdict(context),
            "live": asdict(live),
            "paper_only": True,
            "broker_call_count": session.broker_call_count(),
        }

        with audit_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        print(json.dumps(record, sort_keys=True))
        results.append(record)

        if cycle_no < cycles:
            time.sleep(interval_seconds)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NEDA TEST-024 autonomous live-audited BTC paper trading"
    )
    parser.add_argument(
        "--state", default=str(Path.home() / ".neda" / "test024_state.json")
    )
    parser.add_argument(
        "--audit", default=str(Path.home() / ".neda" / "test024_audit.jsonl")
    )
    parser.add_argument("--history-days", type=int, default=30)
    parser.add_argument("--quantity", type=float, default=1.0)
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args()

    run_session(
        args.state,
        args.audit,
        args.history_days,
        args.quantity,
        args.interval,
        args.cycles,
    )


if __name__ == "__main__":
    main()
