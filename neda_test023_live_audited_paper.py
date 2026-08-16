"""
TEST-023 — Final Live-Audited Paper Trading Gate

This gate audits the SAME Delta Exchange India public REST source used by
NEDA's BTC option provider. It does not replace or parallelize the provider.

Safety:
- read-only public Delta REST;
- no account/order endpoints;
- no broker execution;
- no synthetic/demo fallback;
- raw response bytes are hashed before JSON parsing;
- each audited observation is tied to source URL, observation time and hash.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class LiveDataError(RuntimeError):
    pass


class PaperOnlyViolation(RuntimeError):
    pass


PRODUCTION_REST = "https://api.india.delta.exchange"


@dataclass(frozen=True)
class DeltaLiveObservation:
    observed_at: str
    source: str
    source_url: str
    raw_sha256: str
    symbol: str
    underlying_price: float
    option_count: int
    synthetic: bool = False


@dataclass(frozen=True)
class PaperDecisionAudit:
    observation: DeltaLiveObservation
    signal_reason: str
    entry_reason: str
    selection_reason: str
    risk_reason: str
    action: str
    exit_reason: str | None = None


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fetch_real_delta_btc_options(
    base_url: str = PRODUCTION_REST,
) -> DeltaLiveObservation:
    """
    Fetch the exact public Delta ticker endpoint used by DeltaBTCOptionProvider.

    Failure is fatal. There is no fallback to Binance, demo/testnet, fixtures,
    cached snapshots or generated prices.
    """
    params = {
        "contract_types": "call_options,put_options",
        "underlying_asset_symbols": "BTC",
    }
    query = "?" + urlencode(params)
    path = "/v2/tickers" + query
    url = base_url.rstrip("/") + path

    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "NEDA/TEST-023",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=15) as response:
            raw = response.read()
    except Exception as exc:
        raise LiveDataError("REAL_DELTA_SOURCE_UNAVAILABLE") from exc

    raw_hash = _sha256(raw)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise LiveDataError("REAL_DELTA_SOURCE_INVALID_JSON") from exc

    if payload.get("success") is False:
        raise LiveDataError("REAL_DELTA_API_ERROR")

    rows = payload.get("result")
    if not isinstance(rows, list) or not rows:
        raise LiveDataError("REAL_DELTA_EMPTY_BTC_OPTION_DATA")

    usable = []
    for row in rows:
        symbol = str(row.get("symbol", ""))
        if symbol and (
            str(row.get("contract_type", "")).lower() in {"call_options", "put_options"}
            or symbol.upper().startswith(("C-", "P-"))
        ):
            usable.append(row)

    if not usable:
        raise LiveDataError("REAL_DELTA_NO_BTC_OPTION_ROWS")

    spot = None
    for row in usable:
        candidate = row.get("spot_price") or row.get("underlying_price")
        if candidate not in (None, ""):
            try:
                spot = float(candidate)
            except ValueError:
                continue
            if spot > 0:
                break

    if spot is None:
        raise LiveDataError("REAL_DELTA_NO_VALID_BTC_SPOT")

    return DeltaLiveObservation(
        observed_at=datetime.now(timezone.utc).isoformat(),
        source="DeltaExchangeIndiaPublicREST",
        source_url=url,
        raw_sha256=raw_hash,
        symbol="BTC",
        underlying_price=spot,
        option_count=len(usable),
        synthetic=False,
    )


def require_real_observation(obs: DeltaLiveObservation) -> None:
    if obs.synthetic:
        raise LiveDataError("SYNTHETIC_DATA_REJECTED")
    if not obs.source or not obs.source_url or not obs.raw_sha256:
        raise LiveDataError("OBSERVATION_PROVENANCE_REQUIRED")
    if obs.underlying_price <= 0 or obs.option_count <= 0:
        raise LiveDataError("INVALID_DELTA_OBSERVATION")


def paper_action(action: str) -> str:
    allowed = {"BUY", "SELL_TO_CLOSE", "HOLD", "NO_TRADE"}
    if action not in allowed:
        raise PaperOnlyViolation("UNSUPPORTED_PAPER_ACTION")
    return action


def append_audit(path: str | Path, audit: PaperDecisionAudit) -> None:
    require_real_observation(audit.observation)
    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(audit), sort_keys=True) + "\n")


def save_session_state(path: str | Path, state: dict) -> None:
    payload = dict(state)
    payload["paper_only"] = True
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    Path(path).write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def live_data_boundary_audit(audit_path: str | Path) -> PaperDecisionAudit:
    obs = fetch_real_delta_btc_options()
    require_real_observation(obs)

    # TEST-023 proves the live-data boundary. TEST-017/018/019/020 remain the
    # authoritative decision/execution stack. This first gate records the
    # verified live observation without inventing a trading signal.
    decision = PaperDecisionAudit(
        observation=obs,
        signal_reason="LIVE_DELTA_OBSERVATION_AUDIT",
        entry_reason="WAITING_FOR_EXISTING_STRATEGY_AND_RISK_GATE",
        selection_reason="N/A",
        risk_reason="FINAL_LIVE_DATA_GATE",
        action=paper_action("NO_TRADE"),
        exit_reason=None,
    )
    append_audit(audit_path, decision)
    return decision
