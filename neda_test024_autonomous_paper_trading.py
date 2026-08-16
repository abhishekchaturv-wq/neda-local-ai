"""TEST-024 autonomous, live-audited BTC paper-trading orchestrator.

Removes TEST-022's manual trend/momentum inputs. Historical BTC data is used
to derive the TEST-017 context; the exact live Delta option response used by
the paper runner is captured and hashed for audit.
"""
from __future__ import annotations
import argparse, hashlib, json, math, ssl, statistics, time, urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

try:
    import certifi
except ImportError:
    certifi = None

from btc_options_buyer_strategy import BuyerStrategyContext
from delta_market_data import DeltaBTCOptionProvider, DeltaPublicClient
from neda_test021_session import PersistentPaperTradingSession
from neda_test022_historical_replay import BTCBar, canonical_dataset_hash, validate_bars
from paper_risk_manager import RiskState

BINANCE_URL = "https://api.binance.com/api/v3/klines"

def _tls_context():
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()

def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def _json_get(url, timeout=20.0):
    req = urllib.request.Request(url, headers={"Accept":"application/json","User-Agent":"NEDA/TEST-024"}, method="GET")
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_live_provenance = None

    def _get(self, path, params=None):
        query = "?" + urlencode(params) if params else ""
        url = self.base_url + path + query
        req = urllib.request.Request(url, headers={"Accept":"application/json","User-Agent":"NEDA/TEST-024"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=_tls_context()) as response:
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
            usable = [r for r in rows if str(r.get("symbol","")) and (str(r.get("contract_type","")).lower() in {"call_options","put_options"} or str(r.get("symbol","")).upper().startswith(("C-","P-")))]
            spot = None
            for r in usable:
                value = r.get("spot_price") or r.get("underlying_price")
                try:
                    candidate = float(value)
                except (TypeError, ValueError):
                    continue
                if candidate > 0:
                    spot = candidate
                    break
            if usable and spot is not None:
                self.last_live_provenance = LiveProvenance("DeltaExchangeIndiaPublicREST", url, datetime.now(timezone.utc).isoformat(), raw_hash, len(usable), spot, False)
        return payload

class CachedSnapshotProvider:
    def __init__(self, provider):
        self.provider = provider
        self._cached = None
    def prime(self, snapshot):
        self._cached = snapshot
    def snapshot(self, expiry=None):
        if self._cached is not None:
            snapshot = self._cached
            self._cached = None
            return snapshot
        return self.provider.snapshot(expiry=expiry)

def fetch_historical_btc(history_days=30, interval="1h"):
    if history_days < 7:
        raise ValueError("history_days must be at least 7")
    end_ms = int(time.time()*1000)
    start_ms = end_ms - history_days*24*60*60*1000
    pages = []
    payload_rows = []
    cursor_start = start_ms
    consecutive_short_pages = 0

    while cursor_start <= end_ms:
        url = (
            f"{BINANCE_URL}?symbol=BTCUSDT&interval={interval}"
            f"&startTime={cursor_start}&endTime={end_ms}&limit=1000"
        )

        raw = _json_get(url)
        pages.append(raw)

        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise AutonomousLiveDataError(
                "HISTORICAL_SOURCE_INVALID_JSON"
            ) from exc

        if not isinstance(payload, list):
            raise AutonomousLiveDataError(
                "HISTORICAL_SOURCE_INVALID_PAYLOAD"
            )

        if not payload:
            break

        payload_rows.extend(payload)

        first_ts = int(payload[0][0])
        last_ts = int(payload[-1][0])

        if last_ts < cursor_start:
            raise AutonomousLiveDataError(
                "HISTORICAL_PAGINATION_STALLED"
            )

        if last_ts >= end_ms:
            break

        # Binance normally returns a full page when more data exists.
        # A short page is not immediately treated as complete because
        # TEST-024 explicitly verifies that another page is attempted.
        if len(payload) < 1000:
            consecutive_short_pages += 1
        else:
            consecutive_short_pages = 0

        # Two consecutive short pages without reaching the requested
        # end boundary are treated as the provider's terminal condition.
        # This also prevents a provider repeatedly returning the same
        # short page from causing an infinite pagination loop.
        if consecutive_short_pages >= 2:
            break

        # Advance strictly beyond the last candle received.
        next_cursor = last_ts + 1

        if next_cursor <= cursor_start:
            raise AutonomousLiveDataError(
                "HISTORICAL_PAGINATION_STALLED"
            )

        cursor_start = next_cursor

    if not payload_rows:
        raise AutonomousLiveDataError("HISTORICAL_SOURCE_EMPTY")

    unique = {int(k[0]): k for k in payload_rows}
    selected = [unique[ts] for ts in sorted(unique) if start_ms <= ts <= end_ms]
    rows = [BTCBar(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in selected]
    validate_bars(rows)
    return rows, HistoricalProvenance(
        "Binance Public BTCUSDT Spot Klines",
        f"{BINANCE_URL}?symbol=BTCUSDT&interval={interval}&startTime={start_ms}&endTime={end_ms}&paginated=true",
        datetime.now(timezone.utc).isoformat(),
        _sha256(b"".join(pages)),
        canonical_dataset_hash(rows),
        len(rows),
        False,
    )

def _clip(v): return max(-1.0, min(1.0, v))

def derive_context(rows, live_spot):
    validate_bars(rows)
    if live_spot <= 0:
        raise AutonomousLiveDataError("INVALID_LIVE_BTC_SPOT")
    closes=[r.close for r in rows]
    if len(closes) < 24*7:
        raise AutonomousLiveDataError("INSUFFICIENT_HISTORICAL_CONTEXT")
    window=closes[-24*7:]
    lo,hi=min(window),max(window)
    range_score=0.0 if hi==lo else ((live_spot-lo)/(hi-lo))*2.0-1.0
    ret_6h=live_spot/closes[-7]-1.0
    ret_24h=live_spot/closes[-25]-1.0
    rs=[closes[i]/closes[i-1]-1.0 for i in range(max(1,len(closes)-168),len(closes))]
    vol=statistics.pstdev(rs) if len(rs)>1 else 0.0
    scale=max(vol*math.sqrt(24),0.002)
    momentum=_clip(0.55*(ret_6h/scale)+0.45*(ret_24h/scale))
    mean_30d=statistics.mean(closes[-24*30:]) if len(closes)>=24*30 else statistics.mean(closes)
    trend=_clip(0.65*range_score+0.35*((live_spot/mean_30d-1.0)/0.10))
    return DerivedContext(trend,momentum,0.6*trend+0.4*momentum,len(rows),closes[-1],live_spot,"7D_RANGE+30D_MEAN+6H_24H_RETURN_VOL_NORMALIZATION")

def run_session(state_path,audit_path,history_days=30,quantity=1.0,interval_seconds=60.0,cycles=1):
    if cycles<=0: raise ValueError("cycles must be positive")
    if quantity<=0: raise ValueError("quantity must be positive")
    rows,historical=fetch_historical_btc(history_days)
    client=AuditedDeltaClient()
    provider=DeltaBTCOptionProvider(client=client)
    audited=CachedSnapshotProvider(provider)
    session=PersistentPaperTradingSession(state_path,provider=audited)
    Path(audit_path).parent.mkdir(parents=True,exist_ok=True)
    results=[]
    for cycle_no in range(1,cycles+1):
        live_snapshot=provider.snapshot()
        audited.prime(live_snapshot)
        live=client.last_live_provenance
        if live is None or live.synthetic or live.option_count<=0:
            raise AutonomousLiveDataError("LIVE_DELTA_PROVENANCE_MISSING")
        ctx=derive_context(rows,live.underlying_price)
        result=session.cycle(context=BuyerStrategyContext(ctx.trend_score,ctx.momentum_score),quantity=quantity,risk_state=RiskState(),as_of=datetime.now(timezone.utc).date())
        if session.broker_call_count()!=0:
            raise RuntimeError("SAFETY FAILURE: broker call count is non-zero")
        risk_rejected=result.order_status=="REJECTED" and bool(result.risk_reason)
        record={
            "test":"TEST-024","cycle":cycle_no,"timestamp_utc":datetime.now(timezone.utc).isoformat(),
            "action":result.action,"decision_stage":"RISK_REJECTED" if risk_rejected else result.action,
            "final_action_reason":f"RISK_REJECTED:{result.risk_reason}" if risk_rejected else result.decision_reason,
            "trade_id":result.trade_id,"symbol":result.symbol,"decision_reason":result.decision_reason,
            "entry_reason":result.entry_reason,"selection_reason":result.selection_reason,"risk_reason":result.risk_reason,
            "exit_reason":result.risk_reason if result.action=="SELL_TO_CLOSE" else None,
            "order_status":result.order_status,"fill_price":result.fill_price,
            "historical":asdict(historical),"derived_context":asdict(ctx),"live":asdict(live),
            "paper_only":True,"broker_call_count":session.broker_call_count(),
        }
        with Path(audit_path).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        print(json.dumps(record,sort_keys=True))
        results.append(record)
        if cycle_no<cycles: time.sleep(interval_seconds)
    return results

def main():
    p=argparse.ArgumentParser(description="NEDA TEST-024 autonomous live-audited BTC paper trading")
    p.add_argument("--state",default=str(Path.home()/".neda"/"test024_state.json"))
    p.add_argument("--audit",default=str(Path.home()/".neda"/"test024_audit.jsonl"))
    p.add_argument("--history-days",type=int,default=30)
    p.add_argument("--quantity",type=float,default=1.0)
    p.add_argument("--interval",type=float,default=60.0)
    p.add_argument("--cycles",type=int,default=1)
    args=p.parse_args()
    run_session(args.state,args.audit,args.history_days,args.quantity,args.interval,args.cycles)

if __name__=="__main__": main()
