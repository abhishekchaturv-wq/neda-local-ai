"""NEDA Market Data Adapter V1.

Broker-independent interface for supplying an underlying price and a coherent
option chain. V1 ships only a deterministic demo provider. Live broker
connectors are intentionally deferred to later milestones.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Sequence

from options_engine import OptionSnapshot


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    asset_class: str
    expiry: date
    underlying_price: float
    options: tuple[OptionSnapshot, ...]

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if self.underlying_price <= 0:
            raise ValueError("underlying_price must be positive")
        if any(s.underlying_price != self.underlying_price for s in self.options):
            raise ValueError("all option snapshots must use the market underlying price")
        if any(s.contract.symbol.upper() != self.symbol.upper() for s in self.options):
            raise ValueError("option symbols must match market symbol")
        if any(s.contract.expiry != self.expiry for s in self.options):
            raise ValueError("option expiries must match market expiry")


class MarketDataProvider(ABC):
    """Stable NEDA interface; concrete providers can be broker-specific."""

    @abstractmethod
    def snapshot(self, symbol: str, expiry: date | None = None) -> MarketSnapshot:
        raise NotImplementedError


class DemoMarketDataProvider(MarketDataProvider):
    """Deterministic provider used by the UI and automated tests."""

    def snapshot(self, symbol: str = "NIFTY", expiry: date | None = None) -> MarketSnapshot:
        symbol = symbol.strip().upper()
        expiry = expiry or date(2026, 8, 27)
        underlying = 24520.0
        rows = [
            (24200, 180000, 140000, 22000, 18000),
            (24300, 210000, 165000, 26000, 24000),
            (24400, 265000, 230000, 34000, 32000),
            (24500, 310000, 295000, 41000, 46000),
            (24600, 285000, 330000, 38000, 52000),
            (24700, 220000, 280000, 29000, 43000),
            (24800, 175000, 240000, 21000, 35000),
        ]

        from options_engine import AssetClass, OptionContract, OptionQuote, OptionType

        snapshots: list[OptionSnapshot] = []
        for strike, call_oi, put_oi, call_vol, put_vol in rows:
            snapshots.extend([
                OptionSnapshot(
                    OptionContract(symbol, AssetClass.INDEX, expiry, strike, OptionType.CALL),
                    underlying,
                    OptionQuote(
                        last=max(5.0, underlying - strike + 80),
                        volume=call_vol,
                        open_interest=call_oi,
                        change_in_open_interest=call_oi // 20,
                    ),
                ),
                OptionSnapshot(
                    OptionContract(symbol, AssetClass.INDEX, expiry, strike, OptionType.PUT),
                    underlying,
                    OptionQuote(
                        last=max(5.0, strike - underlying + 80),
                        volume=put_vol,
                        open_interest=put_oi,
                        change_in_open_interest=put_oi // 20,
                    ),
                ),
            ])

        return MarketSnapshot(
            symbol=symbol,
            asset_class="INDEX",
            expiry=expiry,
            underlying_price=underlying,
            options=tuple(snapshots),
        )
