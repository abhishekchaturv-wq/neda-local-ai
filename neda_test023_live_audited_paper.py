"""
TEST-023 — Final Live-Audited Paper Trading Session

Safety boundary:
- Real public BTC market data may be consumed.
- Paper orders only.
- No broker/exchange order submission.
- No synthetic/demo fallback.
- Every market observation used for a decision must carry source + timestamp.
- Session state and journal must persist.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib, json, time
from pathlib import Path
from urllib.request import Request, urlopen


class LiveDataError(RuntimeError):
    pass


class PaperOnlyViolation(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveBTCObservation:
    observed_at: str
    exchange_timestamp_ms: int
    source: str
    source_url: str
    symbol: str
    price: float
    raw_sha256: str
    synthetic: bool = False


@dataclass(frozen=True)
class PaperDecisionAudit:
    observation: LiveBTCObservation
    signal_reason: str
    entry_reason: str
    selection_reason: str
    risk_reason: str
    action: str
    exit_reason: str | None = None


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fetch_real_btc_price(
    source_url: str = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
) -> LiveBTCObservation:
    """
    Fetch a real public BTCUSDT ticker. Failure is fatal.

    There is deliberately NO demo/synthetic fallback.
    """
    req = Request(source_url, headers={"User-Agent": "NEDA-TEST023/1.0"})
    try:
        with urlopen(req, timeout=15) as response:
            raw = response.read()
    except Exception as exc:
        raise LiveDataError("REAL_BTC_SOURCE_UNAVAILABLE") from exc

    raw_hash = _sha256(raw)
    try:
        payload = json.loads(raw.decode("utf-8"))
        price = float(payload["price"])
    except Exception as exc:
        raise LiveDataError("REAL_BTC_SOURCE_INVALID") from exc

    if price <= 0:
        raise LiveDataError("INVALID_BTC_PRICE")

    now = datetime.now(timezone.utc).isoformat()
    # Binance ticker endpoint does not expose an exchange event timestamp.
    # Use local observation time explicitly; never fabricate an exchange time.
    return LiveBTCObservation(
        observed_at=now,
        exchange_timestamp_ms=0,
        source="Binance Public BTCUSDT Spot Ticker",
        source_url=source_url,
        symbol="BTCUSDT",
        price=price,
        raw_sha256=raw_hash,
        synthetic=False,
    )


def require_real_observation(obs: LiveBTCObservation) -> None:
    if obs.synthetic:
        raise LiveDataError("SYNTHETIC_DATA_REJECTED")
    if not obs.source or not obs.source_url or not obs.raw_sha256:
        raise LiveDataError("OBSERVATION_PROVENANCE_REQUIRED")
    if obs.price <= 0:
        raise LiveDataError("INVALID_BTC_PRICE")


def paper_action(action: str) -> str:
    allowed = {"BUY", "SELL_TO_CLOSE", "HOLD", "NO_TRADE"}
    if action not in allowed:
        raise PaperOnlyViolation("UNSUPPORTED_ACTION")
    return action


def append_audit(path: str | Path, audit: PaperDecisionAudit) -> None:
    require_real_observation(audit.observation)
    record = asdict(audit)
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def save_session_state(path: str | Path, state: dict) -> None:
    payload = dict(state)
    payload["paper_only"] = True
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_session_state(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_single_audited_observation(audit_path: str | Path) -> PaperDecisionAudit:
    obs = fetch_real_btc_price()
    require_real_observation(obs)

    # TEST-023 deliberately does not invent a trading signal. The existing
    # TEST-017/018/019/020 stack remains the decision authority. This function
    # proves the live-data boundary and records the observation.
    decision = PaperDecisionAudit(
        observation=obs,
        signal_reason="LIVE_DATA_OBSERVATION_ONLY",
        entry_reason="NO_ENTRY_UNTIL_EXISTING_STRATEGY_AND_RISK_GATE_APPROVE",
        selection_reason="N/A",
        risk_reason="PAPER_ONLY_LIVE_AUDIT_GATE",
        action=paper_action("NO_TRADE"),
        exit_reason=None,
    )
    append_audit(audit_path, decision)
    return decision
