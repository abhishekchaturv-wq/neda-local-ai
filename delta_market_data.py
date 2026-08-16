"""TEST-015 Delta Exchange India public BTC option market data adapter."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from options_engine import AssetClass, OptionContract, OptionQuote, OptionSnapshot, OptionType

PRODUCTION_REST = "https://api.india.delta.exchange"
DEMO_REST = "https://cdn-ind.testnet.deltaex.org"

@dataclass(frozen=True)
class DeltaMarketSnapshot:
    symbol: str
    expiry: date
    underlying_price: float
    options: tuple[OptionSnapshot, ...]
    observed_at_epoch: float
    provider_name: str
    live: bool = True

class DeltaPublicClient:
    """Read-only public REST client. No order/account endpoints exist here."""
    def __init__(self, base_url=PRODUCTION_REST, timeout=10.0, opener: Callable[..., Any] | None=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = opener or urlopen

    def _get(self, path, params=None):
        query = "?" + urlencode(params) if params else ""
        req = Request(self.base_url + path + query,
                      headers={"Accept":"application/json","User-Agent":"NEDA/TEST-015"},
                      method="GET")
        with self._opener(req, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode())
        if payload.get("success") is False:
            raise RuntimeError(f"Delta API error: {payload}")
        return payload

    def products(self, page_size=100):
        return self._get("/v2/products", {"page_size": str(page_size)}).get("result", [])

    def btc_options(self, expiry=None):
        p = {"contract_types":"call_options,put_options",
             "underlying_asset_symbols":"BTC"}
        if expiry:
            p["expiry_date"] = expiry.strftime("%d-%m-%Y")
        result = self._get("/v2/tickers", p).get("result", [])
        return result if isinstance(result, list) else [result]

    def ticker(self, symbol):
        return self._get("/v2/tickers/" + symbol)["result"]

class DeltaBTCOptionProvider:
    def __init__(self, client=None):
        self.client = client or DeltaPublicClient()

    @staticmethod
    def _num(v):
        return None if v in (None, "") else float(v)

    @staticmethod
    def _type(row):
        c = str(row.get("contract_type","")).lower()
        s = str(row.get("symbol","")).upper()
        if "put" in c or s.startswith("P-"): return OptionType.PUT
        if "call" in c or s.startswith("C-"): return OptionType.CALL
        raise ValueError("Cannot determine option type")

    @staticmethod
    def _expiry(row):
        raw = row.get("expiry_date") or row.get("expiry")
        for fmt in ("%d-%m-%Y","%Y-%m-%d","%d/%m/%Y"):
            if raw:
                try: return datetime.strptime(str(raw), fmt).date()
                except ValueError: pass
        tail = str(row.get("symbol","")).rsplit("-",1)[-1]
        if len(tail)==6 and tail.isdigit():
            return datetime.strptime(tail,"%d%m%y").date()
        raise ValueError("Cannot determine expiry")

    @staticmethod
    def _strike(row):
        if row.get("strike_price") is not None: return float(row["strike_price"])
        parts = str(row.get("symbol","")).split("-")
        if len(parts) >= 3: return float(parts[2])
        raise ValueError("Cannot determine strike")

    def snapshot(self, expiry=None):
        rows = self.client.btc_options(expiry)
        snaps = []
        selected = expiry
        underlying = None
        for row in rows:
            ex = self._expiry(row)
            if selected and ex != selected: continue
            selected = selected or ex
            spot = self._num(row.get("spot_price")) or self._num(row.get("underlying_price"))
            if not spot or spot <= 0: continue
            underlying = spot
            q = row.get("quotes") or {}
            greeks = row.get("greeks") or {}
            quote = OptionQuote(
                bid=self._num(q.get("best_bid")),
                ask=self._num(q.get("best_ask")),
                last=self._num(row.get("close")) or self._num(row.get("mark_price")),
                volume=int(float(row["volume"])) if row.get("volume") is not None else None,
                open_interest=int(float(row["oi"])) if row.get("oi") is not None else None,
                implied_volatility=self._num(q.get("bid_iv")) or self._num(q.get("ask_iv"))
            )
            contract = OptionContract("BTC", AssetClass.CRYPTO, ex, self._strike(row), self._type(row))
            snaps.append(OptionSnapshot(contract, spot, quote))
        if not snaps or underlying is None:
            raise ValueError("No usable BTC option quotes returned by Delta")
        normalized = tuple(OptionSnapshot(s.contract, underlying, s.quote, s.greeks, s.timestamp_epoch)
                          for s in snaps)
        return DeltaMarketSnapshot("BTC", selected, underlying, normalized,
                                   datetime.now(timezone.utc).timestamp(),
                                   "DeltaExchangeIndiaPublicREST", True)
