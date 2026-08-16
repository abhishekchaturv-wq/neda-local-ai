"""NEDA Market Data Adapter V1.1.

Provider-neutral market snapshot boundary with explicit freshness metadata.
No broker connectivity is included in this milestone.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
import time

from options_engine import OptionSnapshot


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    asset_class: str
    expiry: date
    underlying_price: float
    options: tuple[OptionSnapshot, ...]
    observed_at_epoch: float
    provider_name: str
    live: bool = False
    stale_after_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if self.underlying_price <= 0:
            raise ValueError("underlying_price must be positive")
        if self.observed_at_epoch <= 0:
            raise ValueError("observed_at_epoch must be positive")
        if self.stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        if not self.provider_name.strip():
            raise ValueError("provider_name cannot be empty")
        if any(s.underlying_price != self.underlying_price for s in self.options):
            raise ValueError("all option snapshots must use the market underlying price")
        if any(s.contract.symbol.upper() != self.symbol.upper() for s in self.options):
            raise ValueError("option symbols must match market symbol")
        if any(s.contract.expiry != self.expiry for s in self.options):
            raise ValueError("option expiries must match market expiry")

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.observed_at_epoch)

    @property
    def is_stale(self) -> bool:
        return self.age_seconds > self.stale_after_seconds


class MarketDataProvider(ABC):
    @abstractmethod
    def snapshot(self, symbol: str, expiry: date | None = None) -> MarketSnapshot:
        raise NotImplementedError


class DemoMarketDataProvider(MarketDataProvider):
    """Deterministic NIFTY/BTC provider used by the UI and automated tests."""

    _CONFIG = {
        "NIFTY": {
            "asset_class": "INDEX",
            "underlying": 24520.0,
            "expiry": date(2026, 8, 27),
            "strikes": [24200, 24300, 24400, 24500, 24600, 24700, 24800],
        },
        "BTC": {
            "asset_class": "CRYPTO",
            "underlying": 118500.0,
            "expiry": date(2026, 8, 28),
            "strikes": [114000, 116000, 118000, 120000, 122000, 124000],
        },
    }

    def snapshot(self, symbol: str = "NIFTY", expiry: date | None = None) -> MarketSnapshot:
        symbol = symbol.strip().upper()
        if symbol not in self._CONFIG:
            raise ValueError(f"unsupported demo symbol: {symbol}")

        cfg = self._CONFIG[symbol]
        expiry = expiry or cfg["expiry"]
        underlying = cfg["underlying"]
        strikes = cfg["strikes"]

        from options_engine import AssetClass, OptionContract, OptionQuote, OptionType

        snapshots: list[OptionSnapshot] = []
        for i, strike in enumerate(strikes):
            # Deterministic synthetic OI/volume profile; this is test/demo data only.
            call_oi = 180000 + i * 21000
            put_oi = 160000 + (len(strikes) - i) * 19000
            call_vol = 22000 + i * 1800
            put_vol = 20000 + (len(strikes) - i) * 1700

            snapshots.extend([
                OptionSnapshot(
                    OptionContract(
                        symbol,
                        AssetClass.INDEX if cfg["asset_class"] == "INDEX" else AssetClass.CRYPTO,
                        expiry,
                        strike,
                        OptionType.CALL,
                    ),
                    underlying,
                    OptionQuote(
                        last=max(5.0, underlying - strike + underlying * 0.002),
                        volume=call_vol,
                        open_interest=call_oi,
                        change_in_open_interest=call_oi // 20,
                    ),
                ),
                OptionSnapshot(
                    OptionContract(
                        symbol,
                        AssetClass.INDEX if cfg["asset_class"] == "INDEX" else AssetClass.CRYPTO,
                        expiry,
                        strike,
                        OptionType.PUT,
                    ),
                    underlying,
                    OptionQuote(
                        last=max(5.0, strike - underlying + underlying * 0.002),
                        volume=put_vol,
                        open_interest=put_oi,
                        change_in_open_interest=put_oi // 20,
                    ),
                ),
            ])

        return MarketSnapshot(
            symbol=symbol,
            asset_class=cfg["asset_class"],
            expiry=expiry,
            underlying_price=underlying,
            options=tuple(snapshots),
            observed_at_epoch=time.time(),
            provider_name="DemoMarketDataProvider",
            live=False,
            stale_after_seconds=30.0,
        )
